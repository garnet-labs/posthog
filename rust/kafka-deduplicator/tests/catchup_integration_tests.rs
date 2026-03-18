//! Integration tests for the catch-up mechanism.
//!
//! These tests verify the catch-up flow: after checkpoint restore, the deduplicator
//! reads the output topic from `producer_offset` to the high watermark, inserting
//! dedup keys into RocksDB. This prevents re-producing events that were already
//! produced by another instance during the gap between checkpoint time and now.
//!
//! Requires Kafka on localhost:9092.
//! Run with: `cargo test --test catchup_integration_tests`

use std::collections::HashMap;
use std::env;
use std::time::Duration;

use anyhow::Result;
use common_types::{CapturedEvent, RawEvent};
use health::HealthRegistry;
use kafka_deduplicator::checkpoint::metadata::CheckpointMetadata;
use kafka_deduplicator::config::Config;
use kafka_deduplicator::pipelines::traits::DeduplicationKeyExtractor;
use kafka_deduplicator::rocksdb::store::RocksDbConfig;
use kafka_deduplicator::service::KafkaDeduplicatorService;
use kafka_deduplicator::store::{DeduplicationStore, DeduplicationStoreConfig};
use kafka_deduplicator::utils::format_store_path;
use rdkafka::admin::{AdminClient, AdminOptions, NewTopic, TopicReplication};
use rdkafka::config::ClientConfig;
use rdkafka::consumer::{BaseConsumer, Consumer};
use rdkafka::message::Message;
use rdkafka::producer::{FutureProducer, FutureRecord, Producer};
use rdkafka::util::Timeout;
use rdkafka::{Offset, TopicPartitionList};
use serde_json::Value;
use tempfile::TempDir;
use uuid::Uuid;

const KAFKA_BROKERS: &str = "localhost:9092";

/// Create test topics with 1 partition each.
async fn create_topics(topics: &[&str]) -> Result<()> {
    let admin_client: AdminClient<_> = ClientConfig::new()
        .set("bootstrap.servers", KAFKA_BROKERS)
        .create()?;

    let new_topics: Vec<NewTopic> = topics
        .iter()
        .map(|t| NewTopic::new(t, 1, TopicReplication::Fixed(1)))
        .collect();

    let opts = AdminOptions::new().operation_timeout(Some(Duration::from_secs(5)));
    let results = admin_client.create_topics(&new_topics, &opts).await?;
    for result in results {
        match result {
            Ok(_) => {}
            Err((_, rdkafka::types::RDKafkaErrorCode::TopicAlreadyExists)) => {}
            Err((topic, err)) => {
                return Err(anyhow::anyhow!("Failed to create topic {topic}: {err:?}"));
            }
        }
    }

    tokio::time::sleep(Duration::from_millis(500)).await;
    Ok(())
}

/// Create a deterministic CapturedEvent with a unique key per index.
fn create_event(index: usize) -> (CapturedEvent, RawEvent) {
    let uuid = Uuid::new_v4();
    let distinct_id = format!("user_{index}");
    let event_name = format!("event_{index}");
    let timestamp = format!("{}", 1700000000 + index as u64);

    let raw_event = RawEvent {
        uuid: Some(uuid),
        distinct_id: Some(serde_json::Value::String(distinct_id.clone())),
        event: event_name.clone(),
        timestamp: Some(timestamp.clone()),
        token: Some("test_token".to_string()),
        properties: HashMap::new(),
        offset: None,
        set: None,
        set_once: None,
    };

    let data = serde_json::to_string(&raw_event).unwrap();

    let captured = CapturedEvent {
        uuid,
        distinct_id,
        session_id: None,
        ip: "127.0.0.1".to_string(),
        data,
        now: format!("{timestamp}000"),
        sent_at: None,
        token: "test_token".to_string(),
        event: event_name,
        timestamp: chrono::Utc::now(),
        is_cookieless_mode: false,
        historical_migration: false,
    };

    (captured, raw_event)
}

/// Produce events to a topic on partition 0.
async fn produce_events(topic: &str, events: &[CapturedEvent]) -> Result<()> {
    let producer: FutureProducer = ClientConfig::new()
        .set("bootstrap.servers", KAFKA_BROKERS)
        .set("message.timeout.ms", "5000")
        .create()?;

    for (i, event) in events.iter().enumerate() {
        let payload = serde_json::to_string(event)?;
        let key = format!("key_{i}");
        let record = FutureRecord::to(topic)
            .key(&key)
            .payload(&payload)
            .partition(0);

        producer
            .send(record, Timeout::After(Duration::from_secs(5)))
            .await
            .map_err(|(e, _)| anyhow::anyhow!("Failed to send message: {e}"))?;
    }

    producer.flush(Timeout::After(Duration::from_secs(5)))?;
    tokio::time::sleep(Duration::from_millis(200)).await;
    Ok(())
}

/// Read all messages from a topic partition using a BaseConsumer (no consumer group).
fn read_all_messages(topic: &str, partition: i32) -> Result<Vec<Value>> {
    let consumer: BaseConsumer = ClientConfig::new()
        .set("bootstrap.servers", KAFKA_BROKERS)
        .set("group.id", format!("verify-{}", Uuid::new_v4()))
        .create()?;

    let (_low, high) = consumer.fetch_watermarks(topic, partition, Duration::from_secs(5))?;
    if high == 0 {
        return Ok(vec![]);
    }

    let mut tpl = TopicPartitionList::new();
    tpl.add_partition_offset(topic, partition, Offset::Beginning)?;
    consumer.assign(&tpl)?;

    let mut messages = Vec::new();
    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(10);

    while messages.len() < high as usize && start.elapsed() < timeout {
        if let Some(Ok(msg)) = consumer.poll(Duration::from_secs(1)) {
            if let Some(payload) = msg.payload() {
                let json: Value = serde_json::from_slice(payload)?;
                messages.push(json);
            }
        }
    }

    Ok(messages)
}

/// Test: Catch-up prevents re-production of events already on the output topic
///
/// Setup:
/// - Input topic: 20 unique events (offsets 0-19)
/// - Output topic: first 15 events (offsets 0-14), as if produced by a previous instance
/// - RocksDB store: dedup keys for events 0-4 (from checkpoint)
/// - metadata.json: consumer_offset=5, producer_offset=5
///
/// Expected flow:
/// 1. Service starts, detects local store with metadata (consumer_offset=5, producer_offset=5)
/// 2. Catch-up reads output topic from offset 5 to 15 (high watermark), inserts keys for events 5-14
/// 3. Store now has keys for events 0-14
/// 4. Consumer resumes from input offset 5, processes events 5-19
/// 5. Events 5-14: already in store (from catch-up) → deduplicated, not re-produced
/// 6. Events 15-19: not in store → produced to output topic
///
/// Verification:
/// - Output topic has exactly 20 messages (15 original + 5 new)
/// - All 20 messages match the original 20 input events
#[tokio::test(flavor = "multi_thread")]
async fn test_catchup_prevents_duplicate_production() -> Result<()> {
    let _ = tracing_subscriber::fmt()
        .with_env_filter("info")
        .with_test_writer()
        .try_init();

    let test_id = Uuid::new_v4();
    let input_topic = format!("catchup_test_input_{test_id}");
    let output_topic = format!("catchup_test_output_{test_id}");
    let group_id = format!("catchup_test_group_{test_id}");

    println!("Test topics: input={input_topic}, output={output_topic}, group={group_id}");

    // Create topics
    create_topics(&[&input_topic, &output_topic]).await?;

    // Generate 20 unique events
    let events: Vec<(CapturedEvent, RawEvent)> = (0..20).map(create_event).collect();
    let captured_events: Vec<CapturedEvent> = events.iter().map(|(c, _)| c.clone()).collect();

    // Step 1: Produce all 20 events to input topic
    println!("Step 1: Producing 20 events to input topic");
    produce_events(&input_topic, &captured_events).await?;

    // Step 2: Produce first 15 events to output topic (simulating previous instance's output)
    println!("Step 2: Producing first 15 events to output topic");
    produce_events(&output_topic, &captured_events[..15]).await?;

    // Step 3: Create RocksDB store with dedup keys for first 5 events
    println!("Step 3: Pre-seeding RocksDB store with keys for events 0-4");
    let store_dir = TempDir::new()?;
    let store_path = format_store_path(store_dir.path(), &input_topic, 0);
    std::fs::create_dir_all(&store_path)?;

    let store_config = DeduplicationStoreConfig {
        path: store_dir.path().to_path_buf(),
        max_capacity: 1_000_000,
        rocksdb: RocksDbConfig::default(),
    };
    let store = DeduplicationStore::new(store_config, input_topic.clone(), 0)?;

    // Insert dedup keys for events 0-4
    for (_captured, raw_event) in events.iter().take(5) {
        let key_bytes = raw_event.extract_dedup_key();
        store.put_timestamp_records_batch(vec![
            kafka_deduplicator::store::deduplication_store::TimestampBatchEntry {
                key: &key_bytes,
                value: &[],
            },
        ])?;
    }

    // Step 4: Write metadata.json with consumer_offset=5, producer_offset=5
    println!("Step 4: Writing metadata.json (consumer_offset=5, producer_offset=5)");
    let mut metadata = CheckpointMetadata::new(
        input_topic.clone(),
        0,
        chrono::Utc::now(),
        1, // sequence
        5, // consumer_offset
        5, // producer_offset
    );
    metadata.write_to_dir(&store_path).await?;

    // Drop the store so the service can open it
    drop(store);

    // Step 5: Configure and start the service with catch-up enabled
    println!("Step 5: Starting service with catch-up enabled");
    env::set_var("KAFKA_CONSUMER_TOPIC", &input_topic);
    env::set_var("KAFKA_CONSUMER_GROUP", &group_id);
    env::set_var("OUTPUT_TOPIC", &output_topic);
    env::set_var("STORE_PATH", store_dir.path().to_str().unwrap());
    env::set_var("KAFKA_CONSUMER_OFFSET_RESET", "earliest");
    env::set_var("COMMIT_INTERVAL_SECS", "1");
    env::set_var("SHUTDOWN_TIMEOUT_SECS", "10");
    env::set_var("KAFKA_PRODUCER_LINGER_MS", "0");
    env::set_var("CATCHUP_ENABLED", "true");
    env::set_var("CATCHUP_BATCH_SIZE", "100");
    env::set_var("CATCHUP_TIMEOUT_SECS", "30");

    let config = Config::init_with_defaults()?;
    let liveness = HealthRegistry::new("test_catchup");
    let service = KafkaDeduplicatorService::new(config, liveness).await?;

    // Run service for a bounded time (needs enough for group join + catch-up + consumption)
    let shutdown_signal = async {
        tokio::time::sleep(Duration::from_secs(15)).await;
    };
    let service_handle =
        tokio::spawn(async move { service.run_with_shutdown(shutdown_signal).await });

    let _ = tokio::time::timeout(Duration::from_secs(20), service_handle).await;
    println!("Service stopped");

    // Step 6: Verify output topic has exactly 20 messages
    println!("Step 6: Verifying output topic contents");
    let output_messages = read_all_messages(&output_topic, 0)?;

    assert_eq!(
        output_messages.len(),
        20,
        "Expected exactly 20 messages on output topic (15 pre-existing + 5 new from events 15-19), got {}",
        output_messages.len()
    );

    // Verify all 20 output messages correspond to the 20 input events by checking UUIDs
    let input_uuids: Vec<String> = events.iter().map(|(c, _)| c.uuid.to_string()).collect();

    let output_uuids: Vec<String> = output_messages
        .iter()
        .filter_map(|msg| msg.get("uuid")?.as_str().map(|s| s.to_string()))
        .collect();

    assert_eq!(
        output_uuids.len(),
        20,
        "Expected 20 UUIDs in output, got {}",
        output_uuids.len()
    );

    // Every input UUID should appear exactly once in the output
    for input_uuid in &input_uuids {
        let count = output_uuids.iter().filter(|u| *u == input_uuid).count();
        assert_eq!(
            count, 1,
            "UUID {input_uuid} should appear exactly once in output, found {count} times"
        );
    }

    println!("All verifications passed: output topic has exactly 20 unique messages");

    Ok(())
}
