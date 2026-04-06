use std::future::Future;
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use rdkafka::error::KafkaError;

use crate::v1::sinks::kafka::producer::{ProduceError, ProduceRecord};
use crate::v1::sinks::SinkName;

/// Mock Kafka producer for testing. Captures sent records and supports
/// configurable error injection and ack delays.
pub struct MockProducer {
    sink: SinkName,
    records: Arc<Mutex<Vec<ProduceRecord>>>,
    send_error: Option<fn() -> ProduceError>,
    ack_error: Option<fn() -> ProduceError>,
    ack_delay: Option<Duration>,
    handle: lifecycle::Handle,
}

impl MockProducer {
    pub fn new(sink: SinkName, handle: lifecycle::Handle) -> Self {
        Self {
            sink,
            records: Arc::new(Mutex::new(Vec::new())),
            send_error: None,
            ack_error: None,
            ack_delay: None,
            handle,
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

    pub fn record_count(&self) -> usize {
        self.records.lock().unwrap().len()
    }

    pub fn with_records<F, R>(&self, f: F) -> R
    where
        F: FnOnce(&[ProduceRecord]) -> R,
    {
        let guard = self.records.lock().unwrap();
        f(&guard)
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

    fn is_ready(&self) -> bool {
        self.handle.is_healthy()
    }

    fn sink_name(&self) -> SinkName {
        self.sink
    }
}
