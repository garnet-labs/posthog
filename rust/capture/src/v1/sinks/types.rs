use std::time::Duration;

use chrono::{DateTime, Utc};
use rdkafka::error::{KafkaError, RDKafkaErrorCode};

/// Kafka topic routing for a processed event.
/// `Drop` means the event should not be produced at all.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub enum Destination {
    #[default]
    AnalyticsMain,
    AnalyticsHistorical,
    Overflow,
    Dlq,
    Custom(String),
    Drop,
}

/// Full configuration for the v1 sink.
#[derive(Clone, Debug)]
pub struct SinkConfig {
    // Topic routing
    pub main_topic: String,
    pub historical_topic: String,
    pub overflow_topic: String,
    pub dlq_topic: String,

    // Kafka client tuning (passed through to rdkafka ClientConfig)
    pub kafka_hosts: String,
    pub kafka_tls: bool,
    pub kafka_compression_codec: String,
    pub producer_linger_ms: u32,
    pub producer_queue_mib: u32,
    pub producer_queue_messages: u32,

    /// Max time to wait for all delivery acks after enqueue.
    pub produce_timeout: Duration,
    // Placeholder for future fallback sink config (S3, etc.)
    // pub fallback: Option<FallbackConfig>,
}

impl SinkConfig {
    pub fn resolve_topic<'a>(&'a self, destination: &'a Destination) -> Option<&'a str> {
        match destination {
            Destination::AnalyticsMain => Some(&self.main_topic),
            Destination::AnalyticsHistorical => Some(&self.historical_topic),
            Destination::Overflow => Some(&self.overflow_topic),
            Destination::Dlq => Some(&self.dlq_topic),
            Destination::Custom(t) => Some(t.as_str()),
            Destination::Drop => None,
        }
    }
}

/// What happened when a publish attempt resolved.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Outcome {
    Success,
    Timeout,
    RetriableError,
    FatalError,
}

/// Backend-agnostic trait for introspecting per-event publish results.
pub trait SinkResult: Send + Sync {
    /// Correlation key -- the originating event's UUID.
    fn key(&self) -> &str;

    fn outcome(&self) -> Outcome;

    /// Human-readable error description, rich with internal details for logging.
    /// None on success.
    fn cause(&self) -> Option<&str>;

    /// Time between batch enqueue start and this event's ack completion.
    fn elapsed(&self) -> chrono::Duration;
}

/// Kafka-specific implementation of [`SinkResult`].
pub struct KafkaResult {
    uuid_key: String,
    outcome: Outcome,
    /// Raw rdkafka error for Kafka-specific introspection. Currently always None
    /// because we go through the v0 `KafkaProducer` trait which maps errors to
    /// `CaptureError`. Will be populated once we have a v1-specific producer.
    kafka_error: Option<KafkaError>,
    /// Pre-formatted cause string built at construction time from whatever error
    /// source is available (rdkafka error codes, serialization failures, timeouts).
    cause: Option<String>,
    /// Batch-level: single `Utc::now()` at the start of publish/publish_batch.
    enqueued_at: DateTime<Utc>,
    /// Per-event: `Utc::now()` when the ack resolved or timeout/error was recorded.
    completed_at: DateTime<Utc>,
}

impl KafkaResult {
    pub(crate) fn new(
        uuid_key: String,
        outcome: Outcome,
        kafka_error: Option<KafkaError>,
        cause: Option<String>,
        enqueued_at: DateTime<Utc>,
        completed_at: DateTime<Utc>,
    ) -> Self {
        Self {
            uuid_key,
            outcome,
            kafka_error,
            cause,
            enqueued_at,
            completed_at,
        }
    }

    /// Raw rdkafka error for Kafka-specific introspection.
    pub fn kafka_error(&self) -> Option<&KafkaError> {
        self.kafka_error.as_ref()
    }

    /// The `RDKafkaErrorCode` if the error originated from rdkafka.
    pub fn error_code(&self) -> Option<RDKafkaErrorCode> {
        self.kafka_error
            .as_ref()
            .and_then(|e| e.rdkafka_error_code())
    }
}

impl SinkResult for KafkaResult {
    fn key(&self) -> &str {
        &self.uuid_key
    }

    fn outcome(&self) -> Outcome {
        self.outcome
    }

    fn cause(&self) -> Option<&str> {
        self.cause.as_deref()
    }

    fn elapsed(&self) -> chrono::Duration {
        self.completed_at.signed_duration_since(self.enqueued_at)
    }
}
