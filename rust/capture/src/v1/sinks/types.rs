use std::borrow::Cow;
use std::collections::HashMap;
use std::fmt;
use std::time::Duration;

use chrono::{DateTime, Utc};
use rdkafka::error::RDKafkaErrorCode;

use crate::config::{CaptureMode, ClusterName, V1KafkaClusterConfig};
use crate::v1::sinks::kafka::producer::ProduceError;

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
            let msg_timeout = Duration::from_millis(cfg.message_timeout_ms as u64);
            anyhow::ensure!(
                self.produce_timeout >= msg_timeout,
                "cluster {}: produce_timeout ({:?}) must be >= message_timeout_ms ({:?}) \
                 to avoid ghost deliveries after application-level timeout",
                name.as_str(),
                self.produce_timeout,
                msg_timeout,
            );
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// error_code_tag
// ---------------------------------------------------------------------------

/// Stable, low-cardinality snake_case tag for an RDKafkaErrorCode.
/// Usable anywhere -- producer, sink, handler, logging.
pub fn error_code_tag(code: RDKafkaErrorCode) -> &'static str {
    match code {
        RDKafkaErrorCode::QueueFull => "queue_full",
        RDKafkaErrorCode::MessageSizeTooLarge => "message_size_too_large",
        RDKafkaErrorCode::MessageTimedOut => "message_timed_out",
        RDKafkaErrorCode::UnknownTopicOrPartition => "unknown_topic_or_partition",
        RDKafkaErrorCode::TopicAuthorizationFailed => "topic_authorization_failed",
        RDKafkaErrorCode::ClusterAuthorizationFailed => "cluster_authorization_failed",
        RDKafkaErrorCode::InvalidMessage => "invalid_message",
        RDKafkaErrorCode::InvalidMessageSize => "invalid_message_size",
        RDKafkaErrorCode::NotLeaderForPartition => "not_leader_for_partition",
        RDKafkaErrorCode::RequestTimedOut => "request_timed_out",
        _ => "rdkafka_other",
    }
}

// ---------------------------------------------------------------------------
// Outcome
// ---------------------------------------------------------------------------

/// What happened when a publish attempt resolved.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Outcome {
    /// Pre-resolution default for metrics emitted before outcome is known.
    InFlight,
    Success,
    Timeout,
    RetriableError,
    FatalError,
}

impl Outcome {
    pub fn as_tag(&self) -> &'static str {
        match self {
            Self::InFlight => "in_flight",
            Self::Success => "success",
            Self::Timeout => "timeout",
            Self::RetriableError => "retriable_error",
            Self::FatalError => "fatal_error",
        }
    }
}

// ---------------------------------------------------------------------------
// SinkResult
// ---------------------------------------------------------------------------

/// Backend-agnostic trait for introspecting per-event publish results.
pub trait SinkResult: Send + Sync {
    /// Correlation key -- the originating event's UUID.
    fn key(&self) -> &str;

    fn outcome(&self) -> Outcome;

    /// Stable, low-cardinality tag for metrics. None on success.
    fn cause(&self) -> Option<&'static str>;

    /// Rich human-readable error detail for logging. None on success.
    fn detail(&self) -> Option<Cow<'_, str>>;

    /// Time between batch enqueue and this event's ack completion.
    /// None if the event never entered the ack path (immediate error).
    fn elapsed(&self) -> Option<chrono::Duration>;
}

// ---------------------------------------------------------------------------
// KafkaSinkError
// ---------------------------------------------------------------------------

/// Full-fidelity error enum capturing every failure mode in the Kafka sink.
/// `SinkResult` trait methods derive their output from this.
#[derive(Debug)]
pub enum KafkaSinkError {
    ClusterNotConfigured,
    ClusterUnavailable,
    SerializationFailed(String),
    Produce(ProduceError),
    Timeout,
    TaskPanicked,
}

impl KafkaSinkError {
    pub fn outcome(&self) -> Outcome {
        match self {
            Self::ClusterNotConfigured => Outcome::FatalError,
            Self::ClusterUnavailable => Outcome::RetriableError,
            Self::SerializationFailed(_) => Outcome::FatalError,
            Self::Produce(e) => {
                if e.is_retriable() {
                    Outcome::RetriableError
                } else {
                    Outcome::FatalError
                }
            }
            Self::Timeout => Outcome::Timeout,
            Self::TaskPanicked => Outcome::RetriableError,
        }
    }

    pub fn as_tag(&self) -> &'static str {
        match self {
            Self::ClusterNotConfigured => "cluster_not_configured",
            Self::ClusterUnavailable => "cluster_unavailable",
            Self::SerializationFailed(_) => "serialization_failed",
            Self::Produce(e) => e.as_tag(),
            Self::Timeout => "timeout",
            Self::TaskPanicked => "task_panicked",
        }
    }

    pub fn detail(&self) -> Cow<'_, str> {
        match self {
            Self::ClusterNotConfigured => Cow::Borrowed("cluster not configured"),
            Self::ClusterUnavailable => Cow::Borrowed("cluster unavailable"),
            Self::SerializationFailed(m) => Cow::Owned(format!("serialization failed: {m}")),
            Self::Produce(e) => Cow::Owned(format!("{e}")),
            Self::Timeout => Cow::Borrowed("produce timeout"),
            Self::TaskPanicked => Cow::Borrowed("task panicked during delivery"),
        }
    }
}

// ---------------------------------------------------------------------------
// KafkaResult
// ---------------------------------------------------------------------------

/// Kafka-specific implementation of [`SinkResult`]. Outcome is derived from
/// the error -- no explicit outcome field.
pub struct KafkaResult {
    uuid_key: String,
    error: Option<KafkaSinkError>,
    enqueued_at: DateTime<Utc>,
    completed_at: Option<DateTime<Utc>>,
}

impl KafkaResult {
    pub(crate) fn ok(uuid_key: String, enqueued_at: DateTime<Utc>) -> Self {
        Self {
            uuid_key,
            error: None,
            enqueued_at,
            completed_at: None,
        }
    }

    pub(crate) fn err(uuid_key: String, error: KafkaSinkError, enqueued_at: DateTime<Utc>) -> Self {
        Self {
            uuid_key,
            error: Some(error),
            enqueued_at,
            completed_at: None,
        }
    }

    pub(crate) fn with_completed_at(mut self, t: DateTime<Utc>) -> Self {
        self.completed_at = Some(t);
        self
    }

    pub fn error(&self) -> Option<&KafkaSinkError> {
        self.error.as_ref()
    }
}

impl SinkResult for KafkaResult {
    fn key(&self) -> &str {
        &self.uuid_key
    }

    fn outcome(&self) -> Outcome {
        match &self.error {
            None => Outcome::Success,
            Some(e) => e.outcome(),
        }
    }

    fn cause(&self) -> Option<&'static str> {
        self.error.as_ref().map(|e| e.as_tag())
    }

    fn detail(&self) -> Option<Cow<'_, str>> {
        self.error.as_ref().map(|e| e.detail())
    }

    fn elapsed(&self) -> Option<chrono::Duration> {
        self.completed_at
            .map(|t| t.signed_duration_since(self.enqueued_at))
    }
}

// ---------------------------------------------------------------------------
// SinkOutput
// ---------------------------------------------------------------------------

/// Concrete enum wrapping backend-specific results. Avoids per-event Box
/// allocation while keeping `Sink` object-safe for `dyn Sink` composition.
pub enum SinkOutput {
    Kafka(KafkaResult),
}

impl SinkResult for SinkOutput {
    fn key(&self) -> &str {
        match self {
            Self::Kafka(r) => r.key(),
        }
    }

    fn outcome(&self) -> Outcome {
        match self {
            Self::Kafka(r) => r.outcome(),
        }
    }

    fn cause(&self) -> Option<&'static str> {
        match self {
            Self::Kafka(r) => r.cause(),
        }
    }

    fn detail(&self) -> Option<Cow<'_, str>> {
        match self {
            Self::Kafka(r) => r.detail(),
        }
    }

    fn elapsed(&self) -> Option<chrono::Duration> {
        match self {
            Self::Kafka(r) => r.elapsed(),
        }
    }
}

// ---------------------------------------------------------------------------
// BatchSummary
// ---------------------------------------------------------------------------

/// Aggregated stats for a batch of publish results.
pub struct BatchSummary {
    pub total: usize,
    pub succeeded: usize,
    pub failed: usize,
    pub timed_out: usize,
    /// Counts keyed by cause tag (e.g. "queue_full", "timeout").
    pub errors: HashMap<String, usize>,
}

impl BatchSummary {
    pub fn from_results(results: &[SinkOutput]) -> Self {
        let mut succeeded = 0usize;
        let mut failed = 0usize;
        let mut timed_out = 0usize;
        let mut errors: HashMap<String, usize> = HashMap::new();

        for r in results {
            match r.outcome() {
                Outcome::Success => succeeded += 1,
                Outcome::Timeout => {
                    timed_out += 1;
                    if let Some(tag) = r.cause() {
                        *errors.entry(tag.to_string()).or_default() += 1;
                    }
                }
                Outcome::RetriableError | Outcome::FatalError => {
                    failed += 1;
                    if let Some(tag) = r.cause() {
                        *errors.entry(tag.to_string()).or_default() += 1;
                    }
                }
                Outcome::InFlight => {}
            }
        }

        Self {
            total: results.len(),
            succeeded,
            failed,
            timed_out,
            errors,
        }
    }

    pub fn all_ok(&self) -> bool {
        self.failed == 0 && self.timed_out == 0
    }
}

impl fmt::Display for BatchSummary {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{} total, {} ok, {} failed, {} timed_out",
            self.total, self.succeeded, self.failed, self.timed_out
        )?;
        if !self.errors.is_empty() {
            let mut pairs: Vec<_> = self.errors.iter().collect();
            pairs.sort_by_key(|(_, count)| std::cmp::Reverse(**count));
            write!(f, " (")?;
            for (i, (tag, count)) in pairs.iter().enumerate() {
                if i > 0 {
                    write!(f, ", ")?;
                }
                write!(f, "{}={}", tag, count)?;
            }
            write!(f, ")")?;
        }
        Ok(())
    }
}
