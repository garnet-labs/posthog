use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use async_trait::async_trait;
use chrono::Utc;
use metrics::{counter, histogram};
use tokio::task::JoinSet;
use tracing::{debug, error, info_span, warn};

use crate::config::CaptureMode;
use crate::v1::context::Context;
use crate::v1::sinks::event::{build_headers, Event};
use crate::v1::sinks::kafka::producer::ProduceRecord;
use crate::v1::sinks::kafka::types::{KafkaResult, KafkaSinkError};
use crate::v1::sinks::kafka::KafkaProducerTrait;
use crate::v1::sinks::types::{BatchSummary, Outcome, SinkOutput};
use crate::v1::sinks::{SinkName, Sinks};

/// Backend-agnostic publishing interface.
#[async_trait]
pub trait Sink: Send + Sync {
    /// Publish a single event to a specific sink. Returns None if the
    /// event was filtered (should_publish false / Destination::Drop).
    async fn publish(
        &self,
        sink: SinkName,
        ctx: &Context,
        event: &(dyn Event + Send + Sync),
    ) -> Option<SinkOutput>;

    /// Publish a batch of events to a specific sink. Returns one SinkOutput
    /// per published event -- skipped events produce no result.
    async fn publish_batch(
        &self,
        sink: SinkName,
        ctx: &Context,
        events: &[&(dyn Event + Send + Sync)],
    ) -> Vec<SinkOutput>;

    /// Which sinks are available for writing.
    fn sinks(&self) -> Vec<SinkName>;

    /// Flush the underlying producer(s) for graceful shutdown.
    fn flush(&self) -> anyhow::Result<()>;
}

pub struct KafkaSink<P: KafkaProducerTrait> {
    producers: HashMap<SinkName, Arc<P>>,
    config: Sinks,
    capture_mode: CaptureMode,
    handle: lifecycle::Handle,
}

impl<P: KafkaProducerTrait> KafkaSink<P> {
    pub fn new(
        producers: HashMap<SinkName, Arc<P>>,
        config: Sinks,
        capture_mode: CaptureMode,
        handle: lifecycle::Handle,
    ) -> Self {
        Self {
            producers,
            config,
            capture_mode,
            handle,
        }
    }
}

fn publish_labels(
    ctx: &Context,
    sink: &str,
    mode: &str,
    outcome: &str,
) -> [(&'static str, String); 5] {
    [
        ("mode", mode.to_string()),
        ("cluster", sink.to_string()), // metric label key kept for dashboard compat
        ("outcome", outcome.to_string()),
        ("path", ctx.path.clone()),
        ("attempt", ctx.attempt.to_string()),
    ]
}

#[async_trait]
impl<P: KafkaProducerTrait + 'static> Sink for KafkaSink<P> {
    async fn publish(
        &self,
        sink: SinkName,
        ctx: &Context,
        event: &(dyn Event + Send + Sync),
    ) -> Option<SinkOutput> {
        let results = self.publish_batch(sink, ctx, &[event]).await;
        results.into_iter().next()
    }

    async fn publish_batch(
        &self,
        sink: SinkName,
        ctx: &Context,
        events: &[&(dyn Event + Send + Sync)],
    ) -> Vec<SinkOutput> {
        let sink_str = sink.as_str();
        let mode = self.capture_mode.as_tag();

        let span = info_span!(
            "v1_publish_batch",
            sink = sink_str,
            mode = mode,
            token = %ctx.api_token,
            path = %ctx.path,
            batch_size = events.len(),
            request_id = %ctx.request_id,
            attempt = ctx.attempt,
        );
        let _guard = span.enter();

        let sink_cfg = match self.config.configs.get(&sink) {
            Some(c) => c,
            None => {
                let enqueued_at = Utc::now();
                let publishable: Vec<_> = events.iter().filter(|e| e.should_publish()).collect();
                counter!(
                    "capture_v1_kafka_publish_total",
                    &publish_labels(ctx, sink_str, mode, Outcome::FatalError.as_tag())[..]
                )
                .increment(publishable.len() as u64);
                return publishable
                    .into_iter()
                    .map(|e| {
                        SinkOutput::Kafka(KafkaResult::err(
                            e.uuid_key().to_string(),
                            KafkaSinkError::SinkNotConfigured,
                            enqueued_at,
                        ))
                    })
                    .collect();
            }
        };
        let producer = &self.producers[&sink];

        // Per-sink health gate
        if !producer.health().is_ready() {
            let enqueued_at = Utc::now();
            let publishable: Vec<_> = events.iter().filter(|e| e.should_publish()).collect();
            counter!(
                "capture_v1_kafka_publish_total",
                &publish_labels(ctx, sink_str, mode, Outcome::RetriableError.as_tag())[..]
            )
            .increment(publishable.len() as u64);
            return publishable
                .into_iter()
                .map(|e| {
                    SinkOutput::Kafka(KafkaResult::err(
                        e.uuid_key().to_string(),
                        KafkaSinkError::SinkUnavailable,
                        enqueued_at,
                    ))
                })
                .collect();
        }

        let enqueued_at = Utc::now();
        let mut results: Vec<SinkOutput> = Vec::new();
        let mut set = JoinSet::new();
        let mut pending_keys: HashSet<String> = HashSet::new();

        // Phase 1: enqueue sequentially to preserve per-partition ordering
        for event in events {
            if !event.should_publish() {
                continue;
            }

            let uuid_key = event.uuid_key().to_string();

            let topic = match sink_cfg.kafka.topic_for(event.destination()) {
                Some(t) => t.to_string(),
                None => continue,
            };

            let payload = match event.serialize(ctx) {
                Ok(p) => p,
                Err(e) => {
                    counter!(
                        "capture_v1_kafka_publish_total",
                        &publish_labels(ctx, sink_str, mode, Outcome::FatalError.as_tag())[..]
                    )
                    .increment(1);
                    results.push(SinkOutput::Kafka(KafkaResult::err(
                        uuid_key,
                        KafkaSinkError::SerializationFailed(e),
                        enqueued_at,
                    )));
                    continue;
                }
            };

            let all_headers = build_headers(ctx, event.headers());
            let mut owned = rdkafka::message::OwnedHeaders::new();
            for (k, v) in &all_headers {
                owned = owned.insert(rdkafka::message::Header {
                    key: k,
                    value: Some(v.as_bytes()),
                });
            }

            let record = ProduceRecord {
                topic,
                key: Some(event.partition_key(ctx)),
                payload,
                headers: owned,
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
                    let sink_err = KafkaSinkError::Produce(e);
                    let outcome = sink_err.outcome();
                    counter!(
                        "capture_v1_kafka_publish_total",
                        &publish_labels(ctx, sink_str, mode, outcome.as_tag())[..]
                    )
                    .increment(1);
                    results.push(SinkOutput::Kafka(KafkaResult::err(
                        uuid_key,
                        sink_err,
                        enqueued_at,
                    )));
                }
            }
        }

        // Phase 2: drain JoinSet with per-sink deadline
        let deadline = tokio::time::Instant::now() + sink_cfg.produce_timeout;
        let mut timed_out = false;

        while !pending_keys.is_empty() {
            match tokio::time::timeout_at(deadline, set.join_next()).await {
                Ok(Some(Ok((uuid_key, completed_at, ack)))) => {
                    pending_keys.remove(&uuid_key);
                    match ack {
                        Ok(()) => {
                            counter!(
                                "capture_v1_kafka_publish_total",
                                &publish_labels(ctx, sink_str, mode, Outcome::Success.as_tag())[..]
                            )
                            .increment(1);
                            let elapsed = completed_at.signed_duration_since(enqueued_at);
                            if let Ok(secs) = elapsed.to_std() {
                                histogram!(
                                    "capture_v1_kafka_ack_duration_seconds",
                                    &publish_labels(ctx, sink_str, mode, Outcome::Success.as_tag())
                                        [..]
                                )
                                .record(secs.as_secs_f64());
                            }
                            results.push(SinkOutput::Kafka(
                                KafkaResult::ok(uuid_key, enqueued_at)
                                    .with_completed_at(completed_at),
                            ));
                        }
                        Err(e) => {
                            let sink_err = KafkaSinkError::Produce(e);
                            let outcome = sink_err.outcome();
                            counter!(
                                "capture_v1_kafka_publish_total",
                                &publish_labels(ctx, sink_str, mode, outcome.as_tag())[..]
                            )
                            .increment(1);
                            results.push(SinkOutput::Kafka(
                                KafkaResult::err(uuid_key, sink_err, enqueued_at)
                                    .with_completed_at(completed_at),
                            ));
                        }
                    }
                }
                Ok(Some(Err(join_err))) => {
                    error!(error = %format!("{join_err:#}"), "join error during publish_batch");
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
            let sink_err_fn: fn() -> KafkaSinkError = if timed_out {
                || KafkaSinkError::Timeout
            } else {
                || KafkaSinkError::TaskPanicked
            };
            let sample_outcome = sink_err_fn().outcome();
            counter!(
                "capture_v1_kafka_publish_total",
                &publish_labels(ctx, sink_str, mode, sample_outcome.as_tag())[..]
            )
            .increment(pending_keys.len() as u64);
            let gave_up_at = if timed_out { Some(Utc::now()) } else { None };
            for uuid_key in pending_keys {
                let mut result = KafkaResult::err(uuid_key, sink_err_fn(), enqueued_at);
                if let Some(t) = gave_up_at {
                    result = result.with_completed_at(t);
                }
                results.push(SinkOutput::Kafka(result));
            }
        }

        let summary = BatchSummary::from_results(&results);
        if summary.all_ok() {
            debug!(%summary, "batch published");
        } else {
            warn!(%summary, "batch had errors");
        }
        for (tag, count) in &summary.errors {
            counter!(
                "capture_v1_kafka_produce_errors_total",
                "cluster" => sink_str.to_string(),
                "mode" => mode.to_string(),
                "error" => tag.clone()
            )
            .increment(*count as u64);
        }

        self.handle.report_healthy();
        results
    }

    fn sinks(&self) -> Vec<SinkName> {
        self.producers.keys().copied().collect()
    }

    fn flush(&self) -> anyhow::Result<()> {
        for (name, producer) in &self.producers {
            let timeout = self
                .config
                .configs
                .get(name)
                .map(|c| c.produce_timeout)
                .unwrap_or(super::constants::DEFAULT_PRODUCE_TIMEOUT);
            producer
                .flush(timeout)
                .map_err(|e| anyhow::anyhow!("{}: flush error: {e:#}", name.as_str()))?;
        }
        Ok(())
    }
}
