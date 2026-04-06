pub mod config;
pub mod context;
pub mod mock;
pub mod producer;
pub mod types;

use std::future::Future;
use std::sync::Arc;
use std::time::Duration;

use rdkafka::error::KafkaError;

use crate::v1::sinks::SinkName;
use context::ProducerHealth;
use producer::{ProduceError, ProduceRecord};

/// Trait abstracting a Kafka producer for testability.
/// `KafkaProducer` is the real impl; `MockProducer` is the test impl.
pub trait KafkaProducerTrait: Send + Sync {
    type Ack: Future<Output = Result<(), ProduceError>> + Send;

    fn send(&self, record: ProduceRecord) -> Result<Self::Ack, ProduceError>;
    fn flush(&self, timeout: Duration) -> Result<(), KafkaError>;
    fn health(&self) -> &Arc<ProducerHealth>;
    fn sink_name(&self) -> SinkName;
}
