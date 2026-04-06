use std::collections::HashMap;
use std::net::{IpAddr, Ipv4Addr};
use std::sync::Arc;
use std::time::Duration;

use axum::http::Method;
use chrono::Utc;
use rdkafka::error::RDKafkaErrorCode;
use uuid::Uuid;

use crate::config::CaptureMode;
use crate::v1::analytics::query::Query;
use crate::v1::context::Context;
use crate::v1::sinks::event::Event;
use crate::v1::sinks::kafka::mock::MockProducer;
use crate::v1::sinks::kafka::producer::ProduceError;
use crate::v1::sinks::sink::{KafkaSink, Sink};
use crate::v1::sinks::types::{BatchSummary, Outcome, SinkResult};
use crate::v1::sinks::{Config, Destination, SinkName, Sinks};

// ---------------------------------------------------------------------------
// FakeEvent
// ---------------------------------------------------------------------------

struct FakeEvent {
    uuid: String,
    publish: bool,
    destination: Destination,
    partition_key: String,
    payload: Result<String, String>,
    event_headers: Vec<(String, String)>,
}

impl FakeEvent {
    fn ok(uuid: &str) -> Self {
        Self {
            uuid: uuid.to_string(),
            publish: true,
            destination: Destination::AnalyticsMain,
            partition_key: format!("phc_test:{uuid}"),
            payload: Ok(r#"{"event":"test"}"#.to_string()),
            event_headers: vec![],
        }
    }

    fn with_destination(mut self, d: Destination) -> Self {
        self.destination = d;
        self
    }

    fn with_publish(mut self, p: bool) -> Self {
        self.publish = p;
        self
    }

    fn with_payload(mut self, p: Result<String, String>) -> Self {
        self.payload = p;
        self
    }
}

impl Event for FakeEvent {
    fn uuid_key(&self) -> &str {
        &self.uuid
    }

    fn should_publish(&self) -> bool {
        self.publish
    }

    fn destination(&self) -> &Destination {
        &self.destination
    }

    fn headers(&self) -> Vec<(String, String)> {
        self.event_headers.clone()
    }

    fn partition_key(&self, _ctx: &Context) -> String {
        self.partition_key.clone()
    }

    fn serialize(&self, _ctx: &Context) -> Result<String, String> {
        self.payload.clone()
    }
}

// ---------------------------------------------------------------------------
// TestHarness
// ---------------------------------------------------------------------------

fn test_context() -> Context {
    Context {
        api_token: "phc_test_token".into(),
        user_agent: "test-agent/1.0".into(),
        content_type: "application/json".into(),
        content_encoding: None,
        sdk_info: "posthog-rust/1.0.0".into(),
        attempt: 1,
        request_id: Uuid::new_v4(),
        client_timestamp: Utc::now(),
        client_ip: IpAddr::V4(Ipv4Addr::LOCALHOST),
        query: Query::default(),
        method: Method::POST,
        path: "/i/v1/general/events".into(),
        server_received_at: Utc::now(),
        created_at: None,
        capture_internal: false,
        historical_migration: false,
    }
}

fn test_kafka_config() -> super::config::Config {
    let env: HashMap<String, String> = [
        ("HOSTS", "localhost:9092"),
        ("TOPIC_MAIN", "events_main"),
        ("TOPIC_HISTORICAL", "events_hist"),
        ("TOPIC_OVERFLOW", "events_overflow"),
        ("TOPIC_DLQ", "events_dlq"),
    ]
    .into_iter()
    .map(|(k, v)| (k.to_string(), v.to_string()))
    .collect();
    envconfig::Envconfig::init_from_hashmap(&env).unwrap()
}

struct TestHarness {
    sink: KafkaSink<MockProducer>,
    producer: Arc<MockProducer>,
    ctx: Context,
    // Keep the manager alive so handles remain valid.
    _manager: lifecycle::Manager,
}

impl TestHarness {
    fn new() -> Self {
        Self::builder().build()
    }

    fn builder() -> HarnessBuilder {
        HarnessBuilder {
            produce_timeout: Duration::from_secs(30),
            send_error: None,
            ack_error: None,
            ack_delay: None,
            not_ready: false,
        }
    }
}

struct HarnessBuilder {
    produce_timeout: Duration,
    send_error: Option<fn() -> ProduceError>,
    ack_error: Option<fn() -> ProduceError>,
    ack_delay: Option<Duration>,
    not_ready: bool,
}

impl HarnessBuilder {
    fn produce_timeout(mut self, d: Duration) -> Self {
        self.produce_timeout = d;
        self
    }

    fn send_error(mut self, f: fn() -> ProduceError) -> Self {
        self.send_error = Some(f);
        self
    }

    fn ack_error(mut self, f: fn() -> ProduceError) -> Self {
        self.ack_error = Some(f);
        self
    }

    fn ack_delay(mut self, d: Duration) -> Self {
        self.ack_delay = Some(d);
        self
    }

    fn not_ready(mut self) -> Self {
        self.not_ready = true;
        self
    }

    fn build(self) -> TestHarness {
        let mut manager = lifecycle::Manager::builder("test")
            .with_trap_signals(false)
            .build();
        let handle = manager.register("kafka_sink_test", lifecycle::ComponentOptions::new());
        handle.report_healthy();

        let mut mock = MockProducer::new(SinkName::Msk, handle.clone());
        if let Some(f) = self.send_error {
            mock = mock.with_send_error(f);
        }
        if let Some(f) = self.ack_error {
            mock = mock.with_ack_error(f);
        }
        if let Some(d) = self.ack_delay {
            mock = mock.with_ack_delay(d);
        }
        if self.not_ready {
            mock = mock.with_not_ready();
        }

        let producer = Arc::new(mock);
        let producers: HashMap<SinkName, Arc<MockProducer>> =
            [(SinkName::Msk, Arc::clone(&producer))]
                .into_iter()
                .collect();

        let sinks_config = Sinks {
            default: SinkName::Msk,
            configs: [(
                SinkName::Msk,
                Config {
                    produce_timeout: self.produce_timeout,
                    kafka: test_kafka_config(),
                },
            )]
            .into_iter()
            .collect(),
        };

        let sink = KafkaSink::new(producers, sinks_config, CaptureMode::Events, handle);

        TestHarness {
            sink,
            producer,
            ctx: test_context(),
            _manager: manager,
        }
    }
}

// ---------------------------------------------------------------------------
// 1. Happy path (single event)
// ---------------------------------------------------------------------------

#[tokio::test]
async fn single_event_success() {
    let h = TestHarness::new();
    let event = FakeEvent::ok("evt-1");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].key(), "evt-1");
    assert_eq!(results[0].outcome(), Outcome::Success);
    assert!(results[0].cause().is_none());
    assert!(results[0].elapsed().is_some());

    assert_eq!(h.producer.record_count(), 1);
    h.producer.with_records(|records| {
        assert_eq!(records[0].topic, "events_main");
        assert_eq!(records[0].payload, r#"{"event":"test"}"#);
        assert_eq!(records[0].key.as_deref(), Some("phc_test:evt-1"));
    });
}

// ---------------------------------------------------------------------------
// 2. Non-publishable events silently skipped
// ---------------------------------------------------------------------------

#[tokio::test]
async fn non_publishable_events_skipped() {
    let h = TestHarness::new();
    let e1 = FakeEvent::ok("evt-1");
    let e2 = FakeEvent::ok("evt-2").with_publish(false);
    let e3 = FakeEvent::ok("evt-3");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&e1, &e2, &e3];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 2);
    assert_eq!(results[0].key(), "evt-1");
    assert_eq!(results[1].key(), "evt-3");
    assert_eq!(h.producer.record_count(), 2);
}

// ---------------------------------------------------------------------------
// 3. Destination::Drop skips without result
// ---------------------------------------------------------------------------

#[tokio::test]
async fn destination_drop_skips_without_result() {
    let h = TestHarness::new();
    let event = FakeEvent::ok("evt-1").with_destination(Destination::Drop);
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert!(results.is_empty());
    assert_eq!(h.producer.record_count(), 0);
}

// ---------------------------------------------------------------------------
// 4. Sink not configured
// ---------------------------------------------------------------------------

#[tokio::test]
async fn sink_not_configured() {
    let h = TestHarness::new();
    let e1 = FakeEvent::ok("evt-1");
    let e2 = FakeEvent::ok("evt-2").with_publish(false);
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&e1, &e2];

    // Request SinkName::Ws, but only Msk is configured
    let results = h.sink.publish_batch(SinkName::Ws, &h.ctx, &events).await;

    // Only the publishable event gets a result
    assert_eq!(results.len(), 1);
    assert_eq!(results[0].key(), "evt-1");
    assert_eq!(results[0].outcome(), Outcome::FatalError);
    assert_eq!(results[0].cause(), Some("sink_not_configured"));
    assert_eq!(h.producer.record_count(), 0);
}

// ---------------------------------------------------------------------------
// 5. Sink unavailable (producer not ready)
// ---------------------------------------------------------------------------

#[tokio::test]
async fn sink_unavailable() {
    let h = TestHarness::builder().not_ready().build();
    let e1 = FakeEvent::ok("evt-1");
    let e2 = FakeEvent::ok("evt-2");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&e1, &e2];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 2);
    for r in &results {
        assert_eq!(r.outcome(), Outcome::RetriableError);
        assert_eq!(r.cause(), Some("sink_unavailable"));
    }
    assert_eq!(h.producer.record_count(), 0);
}

// ---------------------------------------------------------------------------
// 6. Send-time retriable error (queue full)
// ---------------------------------------------------------------------------

#[tokio::test]
async fn send_error_retriable_queue_full() {
    let h = TestHarness::builder()
        .send_error(|| ProduceError::Kafka {
            code: RDKafkaErrorCode::QueueFull,
            retriable: true,
        })
        .build();
    let event = FakeEvent::ok("evt-1");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].key(), "evt-1");
    assert_eq!(results[0].outcome(), Outcome::RetriableError);
    assert_eq!(results[0].cause(), Some("queue_full"));
    assert_eq!(h.producer.record_count(), 0);
}

// ---------------------------------------------------------------------------
// 7. Send-time fatal error (event too big)
// ---------------------------------------------------------------------------

#[tokio::test]
async fn send_error_fatal_event_too_big() {
    let h = TestHarness::builder()
        .send_error(|| ProduceError::EventTooBig {
            message: "too big".into(),
        })
        .build();
    let event = FakeEvent::ok("evt-1");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].outcome(), Outcome::FatalError);
    assert_eq!(results[0].cause(), Some("event_too_big"));
}

// ---------------------------------------------------------------------------
// 8. Ack-time retriable error (delivery cancelled)
// ---------------------------------------------------------------------------

#[tokio::test]
async fn ack_error_retriable_delivery_cancelled() {
    let h = TestHarness::builder()
        .ack_error(|| ProduceError::DeliveryCancelled)
        .build();
    let event = FakeEvent::ok("evt-1");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].key(), "evt-1");
    assert_eq!(results[0].outcome(), Outcome::RetriableError);
    assert_eq!(results[0].cause(), Some("delivery_cancelled"));
    assert!(results[0].elapsed().is_some());
    // Enqueue succeeded before ack failed
    assert_eq!(h.producer.record_count(), 1);
}

// ---------------------------------------------------------------------------
// 9. Ack-time fatal kafka error (topic auth failed)
// ---------------------------------------------------------------------------

#[tokio::test]
async fn ack_error_fatal_topic_auth() {
    let h = TestHarness::builder()
        .ack_error(|| ProduceError::Kafka {
            code: RDKafkaErrorCode::TopicAuthorizationFailed,
            retriable: false,
        })
        .build();
    let event = FakeEvent::ok("evt-1");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].outcome(), Outcome::FatalError);
    assert_eq!(results[0].cause(), Some("topic_authorization_failed"));
    assert!(results[0].elapsed().is_some());
    assert_eq!(h.producer.record_count(), 1);
}

// ---------------------------------------------------------------------------
// 10. Produce timeout
// ---------------------------------------------------------------------------

#[tokio::test]
async fn produce_timeout_single() {
    let h = TestHarness::builder()
        .ack_delay(Duration::from_secs(60))
        .produce_timeout(Duration::from_millis(50))
        .build();
    let event = FakeEvent::ok("evt-1");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].key(), "evt-1");
    assert_eq!(results[0].outcome(), Outcome::Timeout);
    assert_eq!(results[0].cause(), Some("timeout"));
}

#[tokio::test]
async fn produce_timeout_batch_all_pending_get_timeout() {
    let h = TestHarness::builder()
        .ack_delay(Duration::from_secs(60))
        .produce_timeout(Duration::from_millis(50))
        .build();
    let e1 = FakeEvent::ok("evt-1");
    let e2 = FakeEvent::ok("evt-2");
    let e3 = FakeEvent::ok("evt-3");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&e1, &e2, &e3];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 3);
    for r in &results {
        assert_eq!(r.outcome(), Outcome::Timeout);
        assert_eq!(r.cause(), Some("timeout"));
    }
}

// ---------------------------------------------------------------------------
// 11. Serialization failure
// ---------------------------------------------------------------------------

#[tokio::test]
async fn serialization_failure() {
    let h = TestHarness::new();
    let event = FakeEvent::ok("evt-1").with_payload(Err("bad json".into()));
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].key(), "evt-1");
    assert_eq!(results[0].outcome(), Outcome::FatalError);
    assert_eq!(results[0].cause(), Some("serialization_failed"));
    assert!(
        results[0].detail().unwrap().contains("bad json"),
        "expected detail to contain 'bad json', got: {:?}",
        results[0].detail()
    );
    assert_eq!(h.producer.record_count(), 0);
}

// ---------------------------------------------------------------------------
// 12. Mixed batch (some succeed, some fail)
// ---------------------------------------------------------------------------

#[tokio::test]
async fn mixed_batch_success_and_serialize_error() {
    let h = TestHarness::new();
    let e1 = FakeEvent::ok("evt-1");
    let e2 = FakeEvent::ok("evt-2").with_payload(Err("serialize error".into()));
    let e3 = FakeEvent::ok("evt-3");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&e1, &e2, &e3];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 3);

    // Serialization errors are returned inline before ack results, so evt-2
    // appears first in the results vec (pushed during Phase 1), while evt-1
    // and evt-3 are appended during Phase 2 (ack drain). Order among the
    // ack results may vary, so collect into maps.
    let by_key: HashMap<&str, _> = results.iter().map(|r| (r.key(), r)).collect();

    assert_eq!(by_key["evt-1"].outcome(), Outcome::Success);
    assert_eq!(by_key["evt-2"].outcome(), Outcome::FatalError);
    assert_eq!(by_key["evt-2"].cause(), Some("serialization_failed"));
    assert_eq!(by_key["evt-3"].outcome(), Outcome::Success);

    // Only the two successful events were enqueued
    assert_eq!(h.producer.record_count(), 2);
}

// ---------------------------------------------------------------------------
// 13. BatchSummary correctness
// ---------------------------------------------------------------------------

#[tokio::test]
async fn batch_summary_from_mixed_results() {
    let h = TestHarness::new();
    let e1 = FakeEvent::ok("evt-1");
    let e2 = FakeEvent::ok("evt-2").with_payload(Err("ser error".into()));
    let e3 = FakeEvent::ok("evt-3");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&e1, &e2, &e3];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;
    let summary = BatchSummary::from_results(&results);

    assert_eq!(summary.total, 3);
    assert_eq!(summary.succeeded, 2);
    assert_eq!(summary.failed, 1);
    assert_eq!(summary.timed_out, 0);
    assert!(!summary.all_ok());
    assert_eq!(summary.errors.get("serialization_failed").copied(), Some(1));
}

// ---------------------------------------------------------------------------
// 14. Flush delegates to producers
// ---------------------------------------------------------------------------

#[test]
fn flush_ok() {
    let h = TestHarness::new();
    assert!(h.sink.flush().is_ok());
}

// ---------------------------------------------------------------------------
// Topic routing for non-default destinations
// ---------------------------------------------------------------------------

#[tokio::test]
async fn destination_historical_routes_to_correct_topic() {
    let h = TestHarness::new();
    let event = FakeEvent::ok("evt-1").with_destination(Destination::AnalyticsHistorical);
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].outcome(), Outcome::Success);
    h.producer.with_records(|records| {
        assert_eq!(records[0].topic, "events_hist");
    });
}

#[tokio::test]
async fn destination_overflow_routes_to_correct_topic() {
    let h = TestHarness::new();
    let event = FakeEvent::ok("evt-1").with_destination(Destination::Overflow);
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].outcome(), Outcome::Success);
    h.producer.with_records(|records| {
        assert_eq!(records[0].topic, "events_overflow");
    });
}

#[tokio::test]
async fn destination_dlq_routes_to_correct_topic() {
    let h = TestHarness::new();
    let event = FakeEvent::ok("evt-1").with_destination(Destination::Dlq);
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].outcome(), Outcome::Success);
    h.producer.with_records(|records| {
        assert_eq!(records[0].topic, "events_dlq");
    });
}

// ---------------------------------------------------------------------------
// Destination::Custom topic routing
// ---------------------------------------------------------------------------

#[tokio::test]
async fn destination_custom_routes_to_custom_topic() {
    let h = TestHarness::new();
    let event = FakeEvent::ok("evt-1").with_destination(Destination::Custom("my_topic".into()));
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&event];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].outcome(), Outcome::Success);
    h.producer.with_records(|records| {
        assert_eq!(records[0].topic, "my_topic");
    });
}

// ---------------------------------------------------------------------------
// Sink::publish() single-event convenience method
// ---------------------------------------------------------------------------

#[tokio::test]
async fn publish_single_event_success() {
    let h = TestHarness::new();
    let event = FakeEvent::ok("evt-1");

    let result = h.sink.publish(SinkName::Msk, &h.ctx, &event).await;

    assert!(result.is_some());
    let r = result.unwrap();
    assert_eq!(r.key(), "evt-1");
    assert_eq!(r.outcome(), Outcome::Success);
}

#[tokio::test]
async fn publish_single_non_publishable_returns_none() {
    let h = TestHarness::new();
    let event = FakeEvent::ok("evt-1").with_publish(false);

    let result = h.sink.publish(SinkName::Msk, &h.ctx, &event).await;

    assert!(result.is_none());
    assert_eq!(h.producer.record_count(), 0);
}

// ---------------------------------------------------------------------------
// BatchSummary with timeout results
// ---------------------------------------------------------------------------

#[tokio::test]
async fn batch_summary_with_timeouts() {
    let h = TestHarness::builder()
        .ack_delay(Duration::from_secs(60))
        .produce_timeout(Duration::from_millis(50))
        .build();
    let e1 = FakeEvent::ok("evt-1");
    let e2 = FakeEvent::ok("evt-2");
    let events: Vec<&(dyn Event + Send + Sync)> = vec![&e1, &e2];

    let results = h.sink.publish_batch(SinkName::Msk, &h.ctx, &events).await;
    let summary = BatchSummary::from_results(&results);

    assert_eq!(summary.total, 2);
    assert_eq!(summary.succeeded, 0);
    assert_eq!(summary.timed_out, 2);
    assert_eq!(summary.failed, 0);
    assert!(!summary.all_ok());
    assert_eq!(summary.errors.get("timeout").copied(), Some(2));
}
