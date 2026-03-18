//! Catch-up consumer: reads the output topic from a given offset to the high watermark
//! and batch-inserts dedup keys into RocksDB.

use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use rdkafka::consumer::{BaseConsumer, Consumer};
use rdkafka::message::Message;
use rdkafka::{Offset, TopicPartitionList};
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

use crate::config::{Config, PipelineType};
use crate::metrics::MetricsHelper;
use crate::metrics_const::{
    CATCHUP_BATCH_WRITE_DURATION_HISTOGRAM, CATCHUP_DURATION_HISTOGRAM,
    CATCHUP_KEYS_INSERTED_COUNTER, CATCHUP_MESSAGES_PROCESSED_COUNTER, CATCHUP_STATUS_COUNTER,
};
use crate::store::deduplication_store::{DeduplicationStore, TimestampBatchEntry};

use super::extract_dedup_key_value_from_payload;

/// Result of a catch-up operation for a single partition.
#[derive(Debug)]
pub struct CatchupResult {
    pub messages_read: u64,
    pub keys_inserted: u64,
    pub parse_errors: u64,
    pub duration: Duration,
    pub gap_size: i64,
}

/// Run catch-up for a single partition.
///
/// Creates a temporary BaseConsumer, reads the output topic from `start_offset`
/// to the current high watermark, and batch-inserts dedup keys into RocksDB.
///
/// This function is blocking (Kafka poll + RocksDB writes) and should be called
/// from `spawn_blocking`.
pub fn run_catchup(
    config: &Arc<Config>,
    pipeline_type: PipelineType,
    output_topic: &str,
    partition: i32,
    start_offset: i64,
    store: &DeduplicationStore,
    cancel_token: &CancellationToken,
) -> Result<CatchupResult> {
    let metrics = MetricsHelper::new()
        .with_label("topic", output_topic)
        .with_label("partition", &partition.to_string());

    let start_time = Instant::now();

    // Create temporary consumer
    let consumer_config = config.build_catchup_consumer_config();
    let consumer: BaseConsumer = consumer_config
        .create()
        .context("Failed to create catch-up consumer")?;

    // Query high watermark
    let (_low, high) = consumer
        .fetch_watermarks(output_topic, partition, Duration::from_secs(10))
        .context("Failed to fetch watermarks for catch-up")?;

    let gap_size = high - start_offset;

    // No gap to fill
    if high <= start_offset {
        info!(
            output_topic,
            partition,
            start_offset,
            high_watermark = high,
            "Catch-up: no gap to fill"
        );
        metrics
            .counter(CATCHUP_STATUS_COUNTER)
            .with_label("result", "success")
            .increment(1);
        return Ok(CatchupResult {
            messages_read: 0,
            keys_inserted: 0,
            parse_errors: 0,
            duration: start_time.elapsed(),
            gap_size: 0,
        });
    }

    info!(
        output_topic,
        partition,
        start_offset,
        high_watermark = high,
        gap_size,
        "Catch-up: starting"
    );

    // Assign partition at start_offset
    let mut tpl = TopicPartitionList::new();
    tpl.add_partition_offset(output_topic, partition, Offset::Offset(start_offset))
        .context("Failed to add partition to catch-up assignment")?;
    consumer
        .assign(&tpl)
        .context("Failed to assign partition for catch-up")?;

    let timeout = config.catchup_timeout();
    let batch_size = config.catchup_batch_size;
    let poll_timeout = Duration::from_secs(1);

    let mut messages_read: u64 = 0;
    let mut keys_inserted: u64 = 0;
    let mut parse_errors: u64 = 0;
    let mut kv_batch: Vec<(Vec<u8>, Vec<u8>)> = Vec::with_capacity(batch_size);

    loop {
        // Check cancellation
        if cancel_token.is_cancelled() {
            info!(
                output_topic,
                partition, messages_read, keys_inserted, parse_errors, "Catch-up cancelled"
            );
            flush_batch(&kv_batch, store, &metrics, &mut keys_inserted)?;
            metrics
                .counter(CATCHUP_STATUS_COUNTER)
                .with_label("result", "cancelled")
                .increment(1);
            return Ok(build_result(
                messages_read,
                keys_inserted,
                parse_errors,
                start_time,
                gap_size,
            ));
        }

        // Check timeout
        if start_time.elapsed() >= timeout {
            warn!(
                output_topic,
                partition,
                messages_read,
                keys_inserted,
                parse_errors,
                elapsed_secs = start_time.elapsed().as_secs(),
                "Catch-up timeout reached, proceeding with partial results"
            );
            flush_batch(&kv_batch, store, &metrics, &mut keys_inserted)?;
            metrics
                .counter(CATCHUP_STATUS_COUNTER)
                .with_label("result", "timeout")
                .increment(1);
            record_duration(&metrics, start_time, "timeout");
            return Ok(build_result(
                messages_read,
                keys_inserted,
                parse_errors,
                start_time,
                gap_size,
            ));
        }

        // Poll for messages
        match consumer.poll(poll_timeout) {
            Some(Ok(msg)) => {
                let offset = msg.offset();

                if let Some(payload) = msg.payload() {
                    match extract_dedup_key_value_from_payload(pipeline_type, payload) {
                        Ok((key, value)) => {
                            kv_batch.push((key, value));
                            messages_read += 1;
                            metrics
                                .counter(CATCHUP_MESSAGES_PROCESSED_COUNTER)
                                .with_label("result", "success")
                                .increment(1);
                        }
                        Err(e) => {
                            parse_errors += 1;
                            metrics
                                .counter(CATCHUP_MESSAGES_PROCESSED_COUNTER)
                                .with_label("result", "parse_error")
                                .increment(1);
                            debug!(
                                output_topic,
                                partition,
                                offset,
                                error = %e,
                                "Catch-up: failed to parse message, skipping"
                            );
                        }
                    }
                } else {
                    // No payload (tombstone or empty message)
                    metrics
                        .counter(CATCHUP_MESSAGES_PROCESSED_COUNTER)
                        .with_label("result", "skipped")
                        .increment(1);
                }

                // Flush batch when full
                if kv_batch.len() >= batch_size {
                    flush_batch(&kv_batch, store, &metrics, &mut keys_inserted)?;
                    kv_batch.clear();
                }

                // Check if we've reached the high watermark
                if high > 0 && offset >= high - 1 {
                    break;
                }
            }
            Some(Err(e)) => {
                warn!(
                    output_topic,
                    partition,
                    error = %e,
                    "Catch-up: Kafka poll error"
                );
            }
            None => {
                // No message within poll_timeout, loop will check timeout/cancellation
            }
        }
    }

    // Final flush
    flush_batch(&kv_batch, store, &metrics, &mut keys_inserted)?;

    info!(
        output_topic,
        partition,
        messages_read,
        keys_inserted,
        parse_errors,
        duration_secs = start_time.elapsed().as_secs_f64(),
        gap_size,
        "Catch-up completed"
    );

    metrics
        .counter(CATCHUP_STATUS_COUNTER)
        .with_label("result", "success")
        .increment(1);
    record_duration(&metrics, start_time, "success");

    Ok(build_result(
        messages_read,
        keys_inserted,
        parse_errors,
        start_time,
        gap_size,
    ))
}

fn flush_batch(
    kv_batch: &[(Vec<u8>, Vec<u8>)],
    store: &DeduplicationStore,
    metrics: &MetricsHelper,
    keys_inserted: &mut u64,
) -> Result<()> {
    if kv_batch.is_empty() {
        return Ok(());
    }

    let entries: Vec<TimestampBatchEntry> = kv_batch
        .iter()
        .map(|(key, value)| TimestampBatchEntry {
            key: key.as_slice(),
            value: value.as_slice(),
        })
        .collect();

    let batch_start = Instant::now();
    let count = entries.len() as u64;
    store
        .put_timestamp_records_batch(entries)
        .context("Failed to batch-write catch-up keys to RocksDB")?;

    *keys_inserted += count;
    metrics
        .counter(CATCHUP_KEYS_INSERTED_COUNTER)
        .increment(count);
    metrics
        .histogram(CATCHUP_BATCH_WRITE_DURATION_HISTOGRAM)
        .record(batch_start.elapsed().as_secs_f64());

    Ok(())
}

fn build_result(
    messages_read: u64,
    keys_inserted: u64,
    parse_errors: u64,
    start_time: Instant,
    gap_size: i64,
) -> CatchupResult {
    CatchupResult {
        messages_read,
        keys_inserted,
        parse_errors,
        duration: start_time.elapsed(),
        gap_size,
    }
}

fn record_duration(metrics: &MetricsHelper, start_time: Instant, result: &str) {
    metrics
        .histogram(CATCHUP_DURATION_HISTOGRAM)
        .with_label("result", result)
        .record(start_time.elapsed().as_secs_f64());
}
