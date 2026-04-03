use std::future::Future;
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use rdkafka::error::KafkaError;

use crate::config::ClusterName;
use crate::v1::sinks::kafka::context::ProducerHealth;
use crate::v1::sinks::kafka::producer::{ProduceError, ProduceRecord};

/// Mock Kafka producer for testing. Captures sent records and supports
/// configurable error injection and ack delays.
pub struct MockProducer {
    cluster: ClusterName,
    records: Arc<Mutex<Vec<ProduceRecord>>>,
    send_error: Option<fn() -> ProduceError>,
    ack_error: Option<fn() -> ProduceError>,
    ack_delay: Option<Duration>,
    health: Arc<ProducerHealth>,
}

impl MockProducer {
    pub fn new(cluster: ClusterName) -> Self {
        let health = Arc::new(ProducerHealth::new());
        health.set_ready(true);
        Self {
            cluster,
            records: Arc::new(Mutex::new(Vec::new())),
            send_error: None,
            ack_error: None,
            ack_delay: None,
            health,
        }
    }

    pub fn with_send_error(mut self, f: fn() -> ProduceError) -> Self {
        self.send_error = Some(f);
        self
    }

    pub fn with_ack_error(mut self, f: fn() -> ProduceError) -> Self {
        self.ack_error = Some(f);
        self
    }

    pub fn with_ack_delay(mut self, d: Duration) -> Self {
        self.ack_delay = Some(d);
        self
    }

    pub fn with_health_ready(self, ready: bool) -> Self {
        self.health.set_ready(ready);
        self
    }

    pub fn records(&self) -> Vec<ProduceRecord> {
        self.records.lock().unwrap().clone()
    }

    pub fn clear(&self) {
        self.records.lock().unwrap().clear();
    }
}

impl super::KafkaProducerTrait for MockProducer {
    type Ack = Pin<Box<dyn Future<Output = Result<(), ProduceError>> + Send>>;

    fn send(&self, record: ProduceRecord) -> Result<Self::Ack, ProduceError> {
        if let Some(err_fn) = &self.send_error {
            return Err(err_fn());
        }
        self.records.lock().unwrap().push(record);
        let ack_error = self.ack_error;
        let delay = self.ack_delay;
        Ok(Box::pin(async move {
            if let Some(d) = delay {
                tokio::time::sleep(d).await;
            }
            match ack_error {
                Some(err_fn) => Err(err_fn()),
                None => Ok(()),
            }
        }))
    }

    fn flush(&self, _: Duration) -> Result<(), KafkaError> {
        Ok(())
    }

    fn health(&self) -> &Arc<ProducerHealth> {
        &self.health
    }

    fn cluster_name(&self) -> ClusterName {
        self.cluster
    }
}
