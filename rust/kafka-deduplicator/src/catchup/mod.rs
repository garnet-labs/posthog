//! Kafka catch-up mechanism for the deduplicator.
//!
//! After restoring a checkpoint (from S3 or local), the RocksDB state only reflects
//! events up to the checkpoint time. Events produced to the output topic between the
//! checkpoint and now are missing from the store, which would cause them to be
//! re-produced as false non-duplicates.
//!
//! The catch-up mechanism closes this gap by reading the output topic from the
//! checkpoint's `producer_offset` to the current high watermark, extracting dedup
//! keys from each message, and batch-inserting them into RocksDB.
//!
//! ## Configuration
//!
//! - `CATCHUP_ENABLED` (default: false) — master switch
//! - `CATCHUP_BATCH_SIZE` (default: 10000) — RocksDB batch insert size
//! - `CATCHUP_TIMEOUT_SECS` (default: 60) — max time per partition
//! - `CATCHUP_CONSUMER_FETCH_MAX_BYTES` (default: 50MB) — Kafka fetch size

pub mod consumer;

use anyhow::Result;
use common_types::{CapturedEvent, ClickHouseEvent};

use crate::config::PipelineType;
use crate::pipelines::clickhouse_events::ClickHouseEventMetadata;
use crate::pipelines::ingestion_events::{raw_event_from_captured, TimestampMetadata};
use crate::pipelines::traits::{DeduplicationKeyExtractor, DeduplicationMetadata};

/// Extract a dedup key and metadata value from raw Kafka message payload bytes.
///
/// Dispatches to the appropriate parser based on pipeline type, reusing
/// the same parsing and key extraction logic as the normal pipeline path.
///
/// Returns `(key_bytes, value_bytes)` on success, where `value_bytes` is serialized
/// metadata matching the format used by the normal pipeline. This ensures the dedup
/// path can deserialize values from caught-up keys without errors.
pub fn extract_dedup_key_value_from_payload(
    pipeline_type: PipelineType,
    payload: &[u8],
) -> Result<(Vec<u8>, Vec<u8>)> {
    match pipeline_type {
        PipelineType::IngestionEvents => {
            let captured: CapturedEvent = serde_json::from_slice(payload)?;
            let raw_event = raw_event_from_captured(&captured)?;
            let key = raw_event.extract_dedup_key();
            let metadata = TimestampMetadata::new(&raw_event);
            let value = metadata.to_bytes()?;
            Ok((key, value))
        }
        PipelineType::ClickhouseEvents => {
            let event: ClickHouseEvent = serde_json::from_slice(payload)?;
            let key = event.extract_dedup_key();
            let metadata = ClickHouseEventMetadata::new(&event);
            let value = metadata.to_bytes()?;
            Ok((key, value))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use common_types::RawEvent;
    use std::collections::HashMap;
    use uuid::Uuid;

    fn create_captured_event_json(event_name: &str, timestamp: &str) -> Vec<u8> {
        let uuid = Uuid::new_v4();
        let data = serde_json::json!({
            "event": event_name,
            "timestamp": timestamp,
            "properties": {},
        });
        let captured = serde_json::json!({
            "uuid": uuid.to_string(),
            "distinct_id": "user123",
            "ip": "127.0.0.1",
            "data": data.to_string(),
            "now": "2024-01-01T00:00:00Z",
            "token": "test_token",
            "event": event_name,
            "timestamp": "2024-01-01T00:00:00Z",
        });
        serde_json::to_vec(&captured).unwrap()
    }

    fn create_clickhouse_event_json(event_name: &str, timestamp: &str) -> Vec<u8> {
        let uuid = Uuid::new_v4();
        let event = serde_json::json!({
            "uuid": uuid.to_string(),
            "team_id": 123,
            "project_id": 456,
            "event": event_name,
            "distinct_id": "user123",
            "properties": "{\"foo\": \"bar\"}",
            "person_id": "person-uuid",
            "timestamp": timestamp,
            "created_at": "2024-01-01 12:00:00.000000",
            "person_mode": "full",
        });
        serde_json::to_vec(&event).unwrap()
    }

    #[test]
    fn test_ingestion_key_extraction_succeeds() {
        let payload = create_captured_event_json("page_view", "2024-01-01T00:00:00Z");
        let result = extract_dedup_key_value_from_payload(PipelineType::IngestionEvents, &payload);
        assert!(result.is_ok());
        let (key, value) = result.unwrap();
        assert!(!key.is_empty());
        assert!(!value.is_empty());
    }

    #[test]
    fn test_clickhouse_key_extraction_succeeds() {
        let payload = create_clickhouse_event_json("page_view", "2024-01-01 12:00:00.000000");
        let result = extract_dedup_key_value_from_payload(PipelineType::ClickhouseEvents, &payload);
        assert!(result.is_ok());
        let (key, value) = result.unwrap();
        assert!(!key.is_empty());
        assert!(!value.is_empty());
    }

    #[test]
    fn test_invalid_json_returns_error() {
        let result =
            extract_dedup_key_value_from_payload(PipelineType::IngestionEvents, b"not valid json");
        assert!(result.is_err());
    }

    #[test]
    fn test_ingestion_key_consistency_with_normal_pipeline() {
        let uuid = Uuid::new_v4();
        let raw_event = RawEvent {
            uuid: Some(uuid),
            event: "page_view".to_string(),
            distinct_id: Some(serde_json::Value::String("user123".to_string())),
            token: Some("test_token".to_string()),
            properties: HashMap::new(),
            timestamp: Some("2024-01-01T00:00:00Z".to_string()),
            ..Default::default()
        };

        // Normal pipeline key
        let normal_key = raw_event.extract_dedup_key();

        // Catch-up path: serialize as CapturedEvent JSON, then extract
        let captured = CapturedEvent {
            uuid,
            distinct_id: "user123".to_string(),
            session_id: None,
            ip: "127.0.0.1".to_string(),
            data: serde_json::to_string(&raw_event).unwrap(),
            now: "2024-01-01T00:00:00Z".to_string(),
            sent_at: None,
            token: "test_token".to_string(),
            event: "page_view".to_string(),
            timestamp: chrono::Utc::now(),
            is_cookieless_mode: false,
            historical_migration: false,
        };
        let payload = serde_json::to_vec(&captured).unwrap();
        let (catchup_key, _catchup_value) =
            extract_dedup_key_value_from_payload(PipelineType::IngestionEvents, &payload).unwrap();

        assert_eq!(normal_key, catchup_key);
    }

    #[test]
    fn test_clickhouse_key_consistency_with_normal_pipeline() {
        use common_types::PersonMode;

        let uuid = Uuid::new_v4();
        let event = ClickHouseEvent {
            uuid,
            team_id: 123,
            project_id: Some(456),
            event: "test_event".to_string(),
            distinct_id: "user123".to_string(),
            properties: Some(r#"{"foo": "bar"}"#.to_string()),
            person_id: Some("person-uuid".to_string()),
            timestamp: "2024-01-01 12:00:00.000000".to_string(),
            created_at: "2024-01-01 12:00:00.000000".to_string(),
            captured_at: None,
            elements_chain: None,
            person_created_at: None,
            person_properties: None,
            group0_properties: None,
            group1_properties: None,
            group2_properties: None,
            group3_properties: None,
            group4_properties: None,
            group0_created_at: None,
            group1_created_at: None,
            group2_created_at: None,
            group3_created_at: None,
            group4_created_at: None,
            person_mode: PersonMode::Full,
            historical_migration: None,
        };

        let normal_key = event.extract_dedup_key();

        let payload = serde_json::to_vec(&event).unwrap();
        let (catchup_key, _catchup_value) =
            extract_dedup_key_value_from_payload(PipelineType::ClickhouseEvents, &payload).unwrap();

        assert_eq!(normal_key, catchup_key);
    }

    #[test]
    fn test_same_events_produce_same_keys() {
        let payload1 = create_captured_event_json("page_view", "2024-01-01T00:00:00Z");
        let payload2 = create_captured_event_json("page_view", "2024-01-01T00:00:00Z");

        let (key1, _) =
            extract_dedup_key_value_from_payload(PipelineType::IngestionEvents, &payload1).unwrap();
        let (key2, _) =
            extract_dedup_key_value_from_payload(PipelineType::IngestionEvents, &payload2).unwrap();

        // Same event name + timestamp + distinct_id + token = same key
        assert_eq!(key1, key2);
    }

    #[test]
    fn test_different_events_produce_different_keys() {
        let payload1 = create_captured_event_json("page_view", "2024-01-01T00:00:00Z");
        let payload2 = create_captured_event_json("button_click", "2024-01-01T00:00:00Z");

        let (key1, _) =
            extract_dedup_key_value_from_payload(PipelineType::IngestionEvents, &payload1).unwrap();
        let (key2, _) =
            extract_dedup_key_value_from_payload(PipelineType::IngestionEvents, &payload2).unwrap();

        assert_ne!(key1, key2);
    }
}
