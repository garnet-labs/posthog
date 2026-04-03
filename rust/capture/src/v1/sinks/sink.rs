use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use async_trait::async_trait;
use chrono::Utc;
use common_types::CapturedEventHeaders;
use metrics::{counter, histogram};
use tokio::task::JoinSet;
use tracing::{debug, error, info_span, warn};

use crate::config::ClusterName;
use crate::v1::context::Context;
use crate::v1::sinks::event::Event;
use crate::v1::sinks::kafka::producer::{ProduceError, ProduceRecord};
use crate::v1::sinks::kafka::KafkaProducerTrait;
use crate::v1::sinks::types::{BatchSummary, KafkaResult, Outcome, SinkConfig, SinkResult};

/// Backend-agnostic publishing interface.
#[async_trait]
pub trait Sink: Send + Sync {
    /// Publish a single event to a specific cluster.
    async fn publish(
        &self,
        cluster: ClusterName,
        ctx: &Context,
        event: &(dyn Event + Send + Sync),
    ) -> Option<Box<dyn SinkResult>>;

    /// Publish a batch of events to a specific cluster. Returns one SinkResult
    /// per published event -- skipped events produce no result.
    async fn publish_batch(
        &self,
        cluster: ClusterName,
        ctx: &Context,
        events: &[&(dyn Event + Send + Sync)],
    ) -> Vec<Box<dyn SinkResult>>;

    /// Which clusters are available for writing.
    fn clusters(&self) -> Vec<ClusterName>;

    /// Flush the underlying producer(s) for graceful shutdown.
    fn flush(&self) -> Result<(), String>;
}

pub struct KafkaSink<P: KafkaProducerTrait> {
    producers: HashMap<ClusterName, Arc<P>>,
    config: SinkConfig,
    handle: lifecycle::Handle,
}

impl<P: KafkaProducerTrait> KafkaSink<P> {
    pub fn new(
        producers: HashMap<ClusterName, Arc<P>>,
        config: SinkConfig,
        handle: lifecycle::Handle,
    ) -> Self {
        Self {
            producers,
            config,
            handle,
        }
    }

    fn build_headers(
        &self,
        ctx: &Context,
        event: &(dyn Event + Send + Sync),
    ) -> CapturedEventHeaders {
        let event_headers = event.headers();
        let skip_person = event_headers
            .iter()
            .any(|(k, v)| k == "skip_person_processing" && v == "true");

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

fn outcome_from_produce_error(err: &ProduceError) -> Outcome {
    if err.is_retriable() {
        Outcome::RetriableError
    } else {
        Outcome::FatalError
    }
}

#[async_trait]
impl<P: KafkaProducerTrait + 'static> Sink for KafkaSink<P> {
    async fn publish(
        &self,
        cluster: ClusterName,
        ctx: &Context,
        event: &(dyn Event + Send + Sync),
    ) -> Option<Box<dyn SinkResult>> {
        if !event.should_publish() {
            return None;
        }

        let cluster_cfg = match self.config.clusters.get(&cluster) {
            Some(c) => c,
            None => {
                return Some(Box::new(KafkaResult::err(
                    event.uuid_key().to_string(),
                    Outcome::FatalError,
                    None,
                    Some("cluster_not_configured"),
                    Utc::now(),
                )));
            }
        };
        let producer = &self.producers[&cluster];

        let enqueued_at = Utc::now();
        let uuid_key = event.uuid_key().to_string();
        let cluster_str = cluster.as_str();
        let mode = self.config.capture_mode.as_tag();

        if !producer.health().is_ready() {
            counter!("capture_v1_kafka_publish_total",
                "mode" => mode, "cluster" => cluster_str, "outcome" => "retriable_error")
            .increment(1);
            return Some(Box::new(KafkaResult::err(
                uuid_key,
                Outcome::RetriableError,
                None,
                Some("cluster_unavailable"),
                enqueued_at,
            )));
        }

        let topic = match cluster_cfg.topic_for(event.destination()) {
            Some(t) => t.to_string(),
            None => return None,
        };

        let payload = match event.serialize(ctx) {
            Ok(p) => p,
            Err(_) => {
                counter!("capture_v1_kafka_publish_total",
                    "mode" => mode, "cluster" => cluster_str, "outcome" => "fatal_error")
                .increment(1);
                return Some(Box::new(KafkaResult::err(
                    uuid_key,
                    Outcome::FatalError,
                    None,
                    Some("serialization_failed"),
                    enqueued_at,
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

        let ack_future = match producer.send(record) {
            Ok(f) => f,
            Err(e) => {
                let outcome = outcome_from_produce_error(&e);
                counter!("capture_v1_kafka_publish_total",
                    "mode" => mode, "cluster" => cluster_str,
                    "outcome" => if outcome == Outcome::RetriableError { "retriable_error" } else { "fatal_error" })
                .increment(1);
                return Some(Box::new(KafkaResult::err(
                    uuid_key,
                    outcome,
                    e.error_code(),
                    None,
                    enqueued_at,
                )));
            }
        };

        self.handle.report_healthy();

        match tokio::time::timeout(self.config.produce_timeout, ack_future).await {
            Ok(Ok(())) => {
                counter!("capture_v1_kafka_publish_total",
                    "mode" => mode, "cluster" => cluster_str, "outcome" => "success")
                .increment(1);
                Some(Box::new(KafkaResult::ok(uuid_key, enqueued_at)))
            }
            Ok(Err(e)) => {
                let outcome = outcome_from_produce_error(&e);
                counter!("capture_v1_kafka_publish_total",
                    "mode" => mode, "cluster" => cluster_str,
                    "outcome" => if outcome == Outcome::RetriableError { "retriable_error" } else { "fatal_error" })
                .increment(1);
                Some(Box::new(KafkaResult::err(
                    uuid_key,
                    outcome,
                    e.error_code(),
                    None,
                    enqueued_at,
                )))
            }
            Err(_) => {
                counter!("capture_v1_kafka_publish_total",
                    "mode" => mode, "cluster" => cluster_str, "outcome" => "timeout")
                .increment(1);
                Some(Box::new(KafkaResult::err(
                    uuid_key,
                    Outcome::Timeout,
                    None,
                    Some("timeout"),
                    enqueued_at,
                )))
            }
        }
    }

    async fn publish_batch(
        &self,
        cluster: ClusterName,
        ctx: &Context,
        events: &[&(dyn Event + Send + Sync)],
    ) -> Vec<Box<dyn SinkResult>> {
        let cluster_str = cluster.as_str();
        let mode = self.config.capture_mode.as_tag();

        let span = info_span!(
            "v1_publish_batch",
            cluster = cluster_str,
            mode = mode,
            token = %ctx.api_token,
            path = %ctx.path,
            batch_size = events.len(),
            request_id = %ctx.request_id,
            attempt = ctx.attempt,
        );
        let _guard = span.enter();

        let cluster_cfg = match self.config.clusters.get(&cluster) {
            Some(c) => c,
            None => {
                let now = Utc::now();
                return events
                    .iter()
                    .filter(|e| e.should_publish())
                    .map(|e| -> Box<dyn SinkResult> {
                        Box::new(KafkaResult::err(
                            e.uuid_key().to_string(),
                            Outcome::FatalError,
                            None,
                            Some("cluster_not_configured"),
                            now,
                        ))
                    })
                    .collect();
            }
        };
        let producer = &self.producers[&cluster];

        // Per-cluster health gate
        if !producer.health().is_ready() {
            let now = Utc::now();
            counter!("capture_v1_kafka_publish_total",
                "mode" => mode, "cluster" => cluster_str, "outcome" => "retriable_error")
            .increment(events.iter().filter(|e| e.should_publish()).count() as u64);
            return events
                .iter()
                .filter(|e| e.should_publish())
                .map(|e| -> Box<dyn SinkResult> {
                    Box::new(KafkaResult::err(
                        e.uuid_key().to_string(),
                        Outcome::RetriableError,
                        None,
                        Some("cluster_unavailable"),
                        now,
                    ))
                })
                .collect();
        }

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

            let topic = match cluster_cfg.topic_for(event.destination()) {
                Some(t) => t.to_string(),
                None => continue, // Destination::Drop
            };

            let payload = match event.serialize(ctx) {
                Ok(p) => p,
                Err(_e) => {
                    counter!("capture_v1_kafka_publish_total",
                        "mode" => mode, "cluster" => cluster_str, "outcome" => "fatal_error")
                    .increment(1);
                    results.push(Box::new(KafkaResult::err(
                        uuid_key,
                        Outcome::FatalError,
                        None,
                        Some("serialization_failed"),
                        enqueued_at,
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

            match producer.send(record) {
                Ok(ack_future) => {
                    pending_keys.insert(uuid_key.clone());
                    set.spawn(async move {
                        let result = ack_future.await;
                        let completed_at = Utc::now();
                        (uuid_key, completed_at, result)
                    });
                }
                Err(e) => {
                    let outcome = outcome_from_produce_error(&e);
                    let outcome_str = match outcome {
                        Outcome::RetriableError => "retriable_error",
                        _ => "fatal_error",
                    };
                    counter!("capture_v1_kafka_publish_total",
                        "mode" => mode, "cluster" => cluster_str, "outcome" => outcome_str)
                    .increment(1);
                    results.push(Box::new(KafkaResult::err(
                        uuid_key,
                        outcome,
                        e.error_code(),
                        None,
                        enqueued_at,
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
                    let ack_elapsed = completed_at.signed_duration_since(enqueued_at);
                    match ack {
                        Ok(()) => {
                            counter!("capture_v1_kafka_publish_total",
                                "mode" => mode, "cluster" => cluster_str, "outcome" => "success")
                            .increment(1);
                            if let Ok(secs) = ack_elapsed.to_std() {
                                histogram!("capture_v1_kafka_ack_duration_seconds",
                                    "mode" => mode, "cluster" => cluster_str)
                                .record(secs.as_secs_f64());
                            }
                            results.push(Box::new(KafkaResult::ok(uuid_key, enqueued_at)));
                        }
                        Err(e) => {
                            let outcome = outcome_from_produce_error(&e);
                            let outcome_str = match outcome {
                                Outcome::RetriableError => "retriable_error",
                                _ => "fatal_error",
                            };
                            counter!("capture_v1_kafka_publish_total",
                                "mode" => mode, "cluster" => cluster_str, "outcome" => outcome_str)
                            .increment(1);
                            results.push(Box::new(KafkaResult::err(
                                uuid_key,
                                outcome,
                                e.error_code(),
                                None,
                                enqueued_at,
                            )));
                        }
                    }
                }
                Ok(Some(Err(join_err))) => {
                    error!("join error during publish_batch: {join_err:#}");
                }
                Ok(None) => break,
                Err(_) => {
                    timed_out = true;
                    set.abort_all();
                    break;
                }
            }
        }

        // Phase 3: remaining pending keys are from timeout or panicked tasks
        if !pending_keys.is_empty() {
            let (outcome, outcome_str, cause_override): (Outcome, &str, &'static str) = if timed_out
            {
                (Outcome::Timeout, "timeout", "timeout")
            } else {
                (Outcome::RetriableError, "retriable_error", "task_panicked")
            };
            counter!("capture_v1_kafka_publish_total",
                "mode" => mode, "cluster" => cluster_str, "outcome" => outcome_str)
            .increment(pending_keys.len() as u64);
            for uuid_key in pending_keys {
                results.push(Box::new(KafkaResult::err(
                    uuid_key,
                    outcome,
                    None,
                    Some(cause_override),
                    enqueued_at,
                )));
            }
        }

        let summary = BatchSummary::from_results(&results);
        if summary.all_ok() {
            debug!(%summary, "batch published");
        } else {
            warn!(%summary, "batch had errors");
        }
        for (tag, count) in &summary.errors {
            counter!("capture_v1_kafka_produce_errors_total",
                "cluster" => cluster_str, "mode" => mode, "error" => tag.clone())
            .increment(*count as u64);
        }

        self.handle.report_healthy();
        results
    }

    fn clusters(&self) -> Vec<ClusterName> {
        self.producers.keys().copied().collect()
    }

    fn flush(&self) -> Result<(), String> {
        for (name, producer) in &self.producers {
            producer
                .flush(self.config.produce_timeout)
                .map_err(|e| format!("flush {} failed: {e}", name.as_str()))?;
        }
        Ok(())
    }
}
