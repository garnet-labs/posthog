use std::collections::HashMap;
use std::fmt;
use std::time::Duration;

use chrono::{DateTime, Utc};
use rdkafka::error::RDKafkaErrorCode;

use crate::config::{CaptureMode, ClusterName, V1KafkaClusterConfig};
use crate::v1::sinks::kafka::producer::error_code_tag;

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
    error_code: Option<RDKafkaErrorCode>,
    /// Static cause string for non-Kafka errors (timeout, health gate, etc.)
    cause_override: Option<&'static str>,
    enqueued_at: DateTime<Utc>,
    completed_at: DateTime<Utc>,
}

impl KafkaResult {
    pub(crate) fn ok(uuid_key: String, enqueued_at: DateTime<Utc>) -> Self {
        Self {
            uuid_key,
            outcome: Outcome::Success,
            error_code: None,
            cause_override: None,
            enqueued_at,
            completed_at: Utc::now(),
        }
    }

    pub(crate) fn err(
        uuid_key: String,
        outcome: Outcome,
        error_code: Option<RDKafkaErrorCode>,
        cause_override: Option<&'static str>,
        enqueued_at: DateTime<Utc>,
    ) -> Self {
        Self {
            uuid_key,
            outcome,
            error_code,
            cause_override,
            enqueued_at,
            completed_at: Utc::now(),
        }
    }

    pub fn error_code(&self) -> Option<RDKafkaErrorCode> {
        self.error_code
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
        if let Some(o) = self.cause_override {
            return Some(o);
        }
        self.error_code.map(error_code_tag)
    }

    fn elapsed(&self) -> chrono::Duration {
        self.completed_at.signed_duration_since(self.enqueued_at)
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
    pub fn from_results(results: &[Box<dyn SinkResult>]) -> Self {
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
