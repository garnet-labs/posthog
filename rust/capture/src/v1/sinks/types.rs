use std::collections::HashMap;
use std::time::Duration;

use chrono::{DateTime, Utc};
use rdkafka::error::{KafkaError, RDKafkaErrorCode};

use crate::config::{CaptureMode, ClusterName, V1KafkaClusterConfig};

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

impl V1KafkaClusterConfig {
    /// Resolve which topic to use for the given destination on this cluster.
    pub fn topic_for<'a>(&'a self, dest: &'a Destination) -> Option<&'a str> {
        match dest {
            Destination::AnalyticsMain => Some(&self.topic_main),
            Destination::AnalyticsHistorical => Some(&self.topic_historical),
            Destination::Overflow => Some(&self.topic_overflow),
            Destination::Dlq => Some(&self.topic_dlq),
            Destination::Custom(t) => Some(t.as_str()),
            Destination::Drop => None,
        }
    }
}

/// Full configuration for the v1 sink. Each cluster is a complete, independent
/// Kafka setup. The caller (handler/router) decides which cluster(s) to write to.
#[derive(Clone, Debug)]
pub struct SinkConfig {
    pub clusters: HashMap<ClusterName, V1KafkaClusterConfig>,
    pub produce_timeout: Duration,
    pub capture_mode: CaptureMode,
}

impl SinkConfig {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(!self.clusters.is_empty(), "no v1 kafka clusters configured");
        for (&name, cfg) in &self.clusters {
            anyhow::ensure!(
                !cfg.hosts.is_empty(),
                "cluster {} has empty hosts",
                name.as_str()
            );
        }
        Ok(())
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
    kafka_error: Option<KafkaError>,
    cause: Option<String>,
    enqueued_at: DateTime<Utc>,
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

    pub fn kafka_error(&self) -> Option<&KafkaError> {
        self.kafka_error.as_ref()
    }

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
