use std::collections::HashSet;
use std::sync::Arc;

use async_trait::async_trait;
use chrono::Utc;
use common_types::CapturedEventHeaders;
use tokio::task::JoinSet;
use tracing::error;

use crate::api::CaptureError;
use crate::sinks::producer::{KafkaProducer, ProduceRecord};
use crate::v1::context::Context;
use crate::v1::sinks::event::Event;
use crate::v1::sinks::types::{KafkaResult, Outcome, SinkConfig, SinkResult};

/// Backend-agnostic publishing interface. Implementations handle enqueue,
/// delivery ack await (with timeout), and per-event result construction.
#[async_trait]
pub trait Sink: Send + Sync {
    /// Publish a single event. Returns None if `should_publish()` is false.
    /// All failures are captured per-event in the returned `SinkResult`.
    async fn publish(
        &self,
        ctx: &Context,
        event: &(dyn Event + Send + Sync),
    ) -> Option<Box<dyn SinkResult>>;

    /// Publish a batch of events. Enqueues sequentially (preserving rdkafka
    /// per-partition ordering), then awaits all delivery acks concurrently
    /// under `produce_timeout`. Returns one `SinkResult` per published event
    /// only -- skipped events produce no result.
    async fn publish_batch(
        &self,
        ctx: &Context,
        events: &[&(dyn Event + Send + Sync)],
    ) -> Vec<Box<dyn SinkResult>>;

    /// Flush the underlying producer (for graceful shutdown).
    fn flush(&self) -> std::result::Result<(), String>;
}

pub struct KafkaSink<P: KafkaProducer> {
    producer: Arc<P>,
    config: SinkConfig,
    handle: lifecycle::Handle,
}

impl<P: KafkaProducer> KafkaSink<P> {
    pub fn new(producer: Arc<P>, config: SinkConfig, handle: lifecycle::Handle) -> Self {
        Self {
            producer,
            config,
            handle,
        }
    }

    /// Build Kafka headers from Context + Event metadata. The Event's generic
    /// `headers()` pairs are mapped to known `CapturedEventHeaders` fields;
    /// the Sink fills in Context-derived fields.
    fn build_headers(
        &self,
        ctx: &Context,
        event: &(dyn Event + Send + Sync),
    ) -> CapturedEventHeaders {
        let event_headers = event.headers();
        let skip_person = event_headers
            .iter()
            .any(|(k, v)| k == "skip_person_processing" && v == "true");

        // TODO: populate distinct_id, session_id, timestamp, event, uuid from
        // Event trait once serialize() is implemented and we know the field layout.
        CapturedEventHeaders {
            token: Some(ctx.api_token.clone()),
            distinct_id: None,
            session_id: None,
            timestamp: None,
            event: None,
            uuid: None,
            now: Some(ctx.server_received_at.to_rfc3339()),
            force_disable_person_processing: if skip_person { Some(true) } else { None },
            historical_migration: if ctx.historical_migration {
                Some(true)
            } else {
                None
            },
            dlq_reason: None,
            dlq_step: None,
            dlq_timestamp: None,
        }
    }
}

fn outcome_from_capture_error(err: &CaptureError) -> Outcome {
    match err {
        CaptureError::EventTooBig(_) | CaptureError::NonRetryableSinkError => Outcome::FatalError,
        _ => Outcome::RetriableError,
    }
}

#[async_trait]
impl<P: KafkaProducer + 'static> Sink for KafkaSink<P> {
    async fn publish(
        &self,
        ctx: &Context,
        event: &(dyn Event + Send + Sync),
    ) -> Option<Box<dyn SinkResult>> {
        if !event.should_publish() {
            return None;
        }

        let enqueued_at = Utc::now();
        let uuid_key = event.uuid_key().to_string();

        let topic = match self.config.resolve_topic(event.destination()) {
            Some(t) => t.to_string(),
            None => {
                return Some(Box::new(KafkaResult::new(
                    uuid_key,
                    Outcome::FatalError,
                    None,
                    Some("no topic for destination".into()),
                    enqueued_at,
                    Utc::now(),
                )));
            }
        };

        let payload = match event.serialize(ctx) {
            Ok(p) => p,
            Err(e) => {
                return Some(Box::new(KafkaResult::new(
                    uuid_key,
                    Outcome::FatalError,
                    None,
                    Some(format!("serialization failed: {e}")),
                    enqueued_at,
                    Utc::now(),
                )));
            }
        };

        let headers = self.build_headers(ctx, event);
        let record = ProduceRecord {
            topic,
            key: Some(event.partition_key(ctx)),
            payload,
            headers,
        };

        let ack_future = match self.producer.send(record) {
            Ok(f) => f,
            Err(e) => {
                let outcome = outcome_from_capture_error(&e);
                return Some(Box::new(KafkaResult::new(
                    uuid_key,
                    outcome,
                    None,
                    Some(e.to_string()),
                    enqueued_at,
                    Utc::now(),
                )));
            }
        };

        self.handle.report_healthy();

        match tokio::time::timeout(self.config.produce_timeout, ack_future).await {
            Ok(Ok(())) => Some(Box::new(KafkaResult::new(
                uuid_key,
                Outcome::Success,
                None,
                None,
                enqueued_at,
                Utc::now(),
            ))),
            Ok(Err(e)) => {
                let outcome = outcome_from_capture_error(&e);
                Some(Box::new(KafkaResult::new(
                    uuid_key,
                    outcome,
                    None,
                    Some(e.to_string()),
                    enqueued_at,
                    Utc::now(),
                )))
            }
            Err(_) => Some(Box::new(KafkaResult::new(
                uuid_key,
                Outcome::Timeout,
                None,
                Some(format!(
                    "produce timeout after {:?}",
                    self.config.produce_timeout
                )),
                enqueued_at,
                Utc::now(),
            ))),
        }
    }

    async fn publish_batch(
        &self,
        ctx: &Context,
        events: &[&(dyn Event + Send + Sync)],
    ) -> Vec<Box<dyn SinkResult>> {
        let enqueued_at = Utc::now();
        let mut results: Vec<Box<dyn SinkResult>> = Vec::new();
        let mut set = JoinSet::new();
        let mut pending_keys: HashSet<String> = HashSet::new();

        // Phase 1: enqueue sequentially to preserve per-partition ordering
        for event in events {
            if !event.should_publish() {
                continue;
            }

            let uuid_key = event.uuid_key().to_string();

            let topic = match self.config.resolve_topic(event.destination()) {
                Some(t) => t.to_string(),
                None => {
                    results.push(Box::new(KafkaResult::new(
                        uuid_key,
                        Outcome::FatalError,
                        None,
                        Some("no topic for destination".into()),
                        enqueued_at,
                        Utc::now(),
                    )));
                    continue;
                }
            };

            let payload = match event.serialize(ctx) {
                Ok(p) => p,
                Err(e) => {
                    results.push(Box::new(KafkaResult::new(
                        uuid_key,
                        Outcome::FatalError,
                        None,
                        Some(format!("serialization failed: {e}")),
                        enqueued_at,
                        Utc::now(),
                    )));
                    continue;
                }
            };

            let headers = self.build_headers(ctx, *event);
            let record = ProduceRecord {
                topic,
                key: Some(event.partition_key(ctx)),
                payload,
                headers,
            };

            match self.producer.send(record) {
                Ok(ack_future) => {
                    pending_keys.insert(uuid_key.clone());
                    set.spawn(async move {
                        let result = ack_future.await;
                        let completed_at = Utc::now();
                        (uuid_key, completed_at, result)
                    });
                }
                Err(e) => {
                    let outcome = outcome_from_capture_error(&e);
                    results.push(Box::new(KafkaResult::new(
                        uuid_key,
                        outcome,
                        None,
                        Some(e.to_string()),
                        enqueued_at,
                        Utc::now(),
                    )));
                }
            }
        }

        // Phase 2: drain JoinSet with a single deadline for all acks
        let deadline = tokio::time::Instant::now() + self.config.produce_timeout;
        let mut timed_out = false;

        while !pending_keys.is_empty() {
            match tokio::time::timeout_at(deadline, set.join_next()).await {
                Ok(Some(Ok((uuid_key, completed_at, ack)))) => {
                    pending_keys.remove(&uuid_key);
                    match ack {
                        Ok(()) => {
                            results.push(Box::new(KafkaResult::new(
                                uuid_key,
                                Outcome::Success,
                                None,
                                None,
                                enqueued_at,
                                completed_at,
                            )));
                        }
                        Err(e) => {
                            let outcome = outcome_from_capture_error(&e);
                            results.push(Box::new(KafkaResult::new(
                                uuid_key,
                                outcome,
                                None,
                                Some(e.to_string()),
                                enqueued_at,
                                completed_at,
                            )));
                        }
                    }
                }
                Ok(Some(Err(join_err))) => {
                    // Task panicked -- uuid_key is lost in the panic. The orphaned
                    // key stays in pending_keys and gets a RetriableError below.
                    error!("join error during publish_batch: {join_err:#}");
                }
                Ok(None) => {
                    break;
                }
                Err(_) => {
                    timed_out = true;
                    set.abort_all();
                    break;
                }
            }
        }

        // Phase 3: any remaining pending keys are from timeout or panicked tasks
        if !pending_keys.is_empty() {
            let completed_at = Utc::now();
            let (outcome, cause) = if timed_out {
                (
                    Outcome::Timeout,
                    format!("produce timeout after {:?}", self.config.produce_timeout),
                )
            } else {
                (
                    Outcome::RetriableError,
                    "task panicked during delivery".into(),
                )
            };
            for uuid_key in pending_keys {
                results.push(Box::new(KafkaResult::new(
                    uuid_key,
                    outcome,
                    None,
                    Some(cause.clone()),
                    enqueued_at,
                    completed_at,
                )));
            }
        }

        self.handle.report_healthy();
        results
    }

    fn flush(&self) -> std::result::Result<(), String> {
        self.producer.flush().map_err(|e| e.to_string())
    }
}
