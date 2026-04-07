use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use async_trait::async_trait;
use chrono::Utc;
use futures::stream::FuturesUnordered;
use futures::StreamExt;
use metrics::{counter, histogram};
use tracing::{debug, info_span, Level};

use crate::config::CaptureMode;
use crate::v1::context::Context;
use crate::v1::sinks::event::{build_context_headers, Event};
use crate::v1::sinks::sink::Sink;
use crate::v1::sinks::types::{BatchSummary, Outcome, SinkResult};
use crate::v1::sinks::{SinkName, Sinks};

use super::producer::ProduceRecord;
use super::types::{KafkaResult, KafkaSinkError};
use super::KafkaProducerTrait;

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

/// Reject every publishable event in `events` with the same error,
/// incrementing a single counter for the batch. Used for pre-flight
/// failures (sink not configured, producer not ready).
fn reject_publishable(
    events: &[&(dyn Event + Send + Sync)],
    error_fn: fn() -> KafkaSinkError,
    sink_str: &'static str,
    mode: &'static str,
    path: &str,
    attempt: &str,
) -> Vec<Box<dyn SinkResult>> {
    let enqueued_at = Utc::now();
    let outcome = error_fn().outcome();
    let publishable: Vec<_> = events.iter().filter(|e| e.should_publish()).collect();
    counter!(
        "capture_v1_kafka_publish_total",
        "mode" => mode,
        "cluster" => sink_str,
        "outcome" => outcome.as_tag(),
        "path" => path.to_owned(),
        "attempt" => attempt.to_owned(),
    )
    .increment(publishable.len() as u64);
    publishable
        .into_iter()
        .map(|e| -> Box<dyn SinkResult> {
            Box::new(KafkaResult::err(
                e.uuid_key().to_string(),
                error_fn(),
                enqueued_at,
            ))
        })
        .collect()
}

#[async_trait]
impl<P: KafkaProducerTrait + 'static> Sink for KafkaSink<P> {
    async fn publish(
        &self,
        sink: SinkName,
        ctx: &Context,
        event: &(dyn Event + Send + Sync),
    ) -> Option<Box<dyn SinkResult>> {
        let results = self.publish_batch(sink, ctx, &[event]).await;
        results.into_iter().next()
    }

    async fn publish_batch(
        &self,
        sink: SinkName,
        ctx: &Context,
        events: &[&(dyn Event + Send + Sync)],
    ) -> Vec<Box<dyn SinkResult>> {
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

        // Pre-compute label values used across all counter calls in this batch.
        // `sink_str` and `mode` are &'static str (zero-cost); only path/attempt allocate.
        let path = ctx.path.clone();
        let attempt = ctx.attempt.to_string();

        let sink_cfg = match self.config.configs.get(&sink) {
            Some(c) => c,
            None => {
                crate::ctx_log!(
                    Level::ERROR,
                    ctx,
                    sink = sink_str,
                    "sink not configured — rejecting batch"
                );
                return reject_publishable(
                    events,
                    || KafkaSinkError::SinkNotConfigured,
                    sink_str,
                    mode,
                    &path,
                    &attempt,
                );
            }
        };
        let producer = &self.producers[&sink];

        // Per-sink health gate
        if !producer.is_ready() {
            crate::ctx_log!(
                Level::ERROR,
                ctx,
                sink = sink_str,
                "producer not ready — rejecting batch"
            );
            return reject_publishable(
                events,
                || KafkaSinkError::SinkUnavailable,
                sink_str,
                mode,
                &path,
                &attempt,
            );
        }

        // Pre-compute context-level headers once for the batch.
        let ctx_headers = build_context_headers(ctx);

        let enqueued_at = Utc::now();
        let mut results: Vec<Box<dyn SinkResult>> = Vec::new();
        // FuturesUnordered polls ack futures inline — no per-event tokio::spawn.
        // DeliveryFuture is a oneshot receiver (pure I/O wait, no CPU work), so
        // single-task polling is strictly cheaper than spawning real tasks.
        let mut pending = FuturesUnordered::new();
        let mut enqueued_keys: Vec<String> = Vec::new();

        // Reusable buffers — cleared each iteration, amortised to zero allocs
        // after the first event.
        let mut payload_buf = String::with_capacity(4096);
        let mut key_buf = String::with_capacity(128);

        // Phase 1: enqueue sequentially to preserve per-partition ordering
        for event in events {
            if !event.should_publish() {
                continue;
            }

            let uuid_key = event.uuid_key().to_string();

            let topic = match sink_cfg.kafka.topic_for(event.destination()) {
                Some(t) => t,
                None => continue,
            };

            payload_buf.clear();
            if let Err(e) = event.serialize_into(ctx, &mut payload_buf) {
                counter!(
                    "capture_v1_kafka_publish_total",
                    "mode" => mode,
                    "cluster" => sink_str,
                    "outcome" => Outcome::FatalError.as_tag(),
                    "path" => path.clone(),
                    "attempt" => attempt.clone(),
                )
                .increment(1);
                results.push(Box::new(KafkaResult::err(
                    uuid_key,
                    KafkaSinkError::SerializationFailed(e),
                    enqueued_at,
                )));
                continue;
            }

            // Build OwnedHeaders from scratch per event (avoids cloning a base).
            let mut headers = rdkafka::message::OwnedHeaders::new();
            for (k, v) in &ctx_headers {
                headers = headers.insert(rdkafka::message::Header {
                    key: k,
                    value: Some(v.as_bytes()),
                });
            }
            for (k, v) in &event.headers() {
                headers = headers.insert(rdkafka::message::Header {
                    key: k,
                    value: Some(v.as_bytes()),
                });
            }

            key_buf.clear();
            event.write_partition_key(ctx, &mut key_buf);

            let record = ProduceRecord {
                topic,
                key: Some(&key_buf),
                payload: &payload_buf,
                headers,
            };

            match producer.send(record) {
                Ok(ack_future) => {
                    enqueued_keys.push(uuid_key.clone());
                    pending.push(async move {
                        let result = ack_future.await;
                        (uuid_key, Utc::now(), result)
                    });
                }
                Err(e) => {
                    let sink_err = KafkaSinkError::Produce(e);
                    let outcome = sink_err.outcome();
                    counter!(
                        "capture_v1_kafka_publish_total",
                        "mode" => mode,
                        "cluster" => sink_str,
                        "outcome" => outcome.as_tag(),
                        "path" => path.clone(),
                        "attempt" => attempt.clone(),
                    )
                    .increment(1);
                    results.push(Box::new(KafkaResult::err(uuid_key, sink_err, enqueued_at)));
                }
            }
        }

        // Phase 2: drain ack futures with per-sink deadline.
        // Dropping remaining futures on timeout is safe: the underlying
        // DeliveryFuture is a oneshot::Receiver — dropping it just means
        // rdkafka's delivery callback send() returns Err (silently ignored).
        // The message still completes in librdkafka (or times out via
        // message.timeout.ms); we just stop waiting for the ack.
        let deadline = tokio::time::Instant::now() + sink_cfg.produce_timeout;
        let mut resolved_keys: HashSet<String> = HashSet::new();

        loop {
            match tokio::time::timeout_at(deadline, pending.next()).await {
                Ok(Some((uuid_key, completed_at, ack))) => {
                    resolved_keys.insert(uuid_key.clone());
                    match ack {
                        Ok(()) => {
                            counter!(
                                "capture_v1_kafka_publish_total",
                                "mode" => mode,
                                "cluster" => sink_str,
                                "outcome" => Outcome::Success.as_tag(),
                                "path" => path.clone(),
                                "attempt" => attempt.clone(),
                            )
                            .increment(1);
                            let elapsed = completed_at.signed_duration_since(enqueued_at);
                            if let Ok(secs) = elapsed.to_std() {
                                histogram!(
                                    "capture_v1_kafka_ack_duration_seconds",
                                    "mode" => mode,
                                    "cluster" => sink_str,
                                    "outcome" => Outcome::Success.as_tag(),
                                    "path" => path.clone(),
                                    "attempt" => attempt.clone(),
                                )
                                .record(secs.as_secs_f64());
                            }
                            results.push(Box::new(
                                KafkaResult::ok(uuid_key, enqueued_at)
                                    .with_completed_at(completed_at),
                            ));
                        }
                        Err(e) => {
                            let sink_err = KafkaSinkError::Produce(e);
                            let outcome = sink_err.outcome();
                            counter!(
                                "capture_v1_kafka_publish_total",
                                "mode" => mode,
                                "cluster" => sink_str,
                                "outcome" => outcome.as_tag(),
                                "path" => path.clone(),
                                "attempt" => attempt.clone(),
                            )
                            .increment(1);
                            results.push(Box::new(
                                KafkaResult::err(uuid_key, sink_err, enqueued_at)
                                    .with_completed_at(completed_at),
                            ));
                        }
                    }
                }
                Ok(None) => break,
                Err(_) => break,
            }
        }

        // Phase 3: keys enqueued but not resolved are timed-out events.
        // (With FuturesUnordered, the only way to have residue is a deadline
        // break — there are no JoinErrors / task panics to handle.)
        let timed_out_keys: Vec<_> = enqueued_keys
            .into_iter()
            .filter(|k| !resolved_keys.contains(k))
            .collect();
        if !timed_out_keys.is_empty() {
            counter!(
                "capture_v1_kafka_publish_total",
                "mode" => mode,
                "cluster" => sink_str,
                "outcome" => Outcome::Timeout.as_tag(),
                "path" => path.clone(),
                "attempt" => attempt.clone(),
            )
            .increment(timed_out_keys.len() as u64);
            let gave_up_at = Utc::now();
            for uuid_key in timed_out_keys {
                results.push(Box::new(
                    KafkaResult::err(uuid_key, KafkaSinkError::Timeout, enqueued_at)
                        .with_completed_at(gave_up_at),
                ));
            }
        }

        let summary = BatchSummary::from_results(&results);
        if summary.all_ok() {
            debug!(%summary, "batch published");
        } else if summary.succeeded == 0 {
            crate::ctx_log!(Level::ERROR, ctx,
                sink = sink_str,
                %summary,
                errors = ?summary.errors,
                "batch fully failed");
        } else {
            crate::ctx_log!(Level::WARN, ctx,
                sink = sink_str,
                %summary,
                errors = ?summary.errors,
                "batch partially failed");
        }
        for (tag, count) in &summary.errors {
            counter!(
                "capture_v1_kafka_produce_errors_total",
                "cluster" => sink_str,
                "mode" => mode,
                "error" => tag.clone()
            )
            .increment(*count as u64);
        }

        if summary.succeeded > 0 {
            self.handle.report_healthy();
        }
        results
    }

    fn sinks(&self) -> Vec<SinkName> {
        self.producers.keys().copied().collect()
    }

    async fn flush(&self) -> anyhow::Result<()> {
        let mut set = tokio::task::JoinSet::new();
        for (name, producer) in &self.producers {
            let timeout = self
                .config
                .configs
                .get(name)
                .map(|c| c.produce_timeout)
                .unwrap_or(crate::v1::sinks::constants::DEFAULT_PRODUCE_TIMEOUT);
            let producer = producer.clone();
            let name_str = name.as_str();
            set.spawn_blocking(move || {
                producer
                    .flush(timeout)
                    .map_err(|e| anyhow::anyhow!("{name_str}: flush error: {e:#}"))
            });
        }
        let mut first_err: Option<anyhow::Error> = None;
        while let Some(result) = set.join_next().await {
            if let Err(e) = result
                .map_err(|e| anyhow::anyhow!("flush task panicked: {e:#}"))
                .and_then(|r| r)
            {
                if first_err.is_none() {
                    first_err = Some(e);
                }
            }
        }
        match first_err {
            Some(e) => Err(e),
            None => Ok(()),
        }
    }
}
