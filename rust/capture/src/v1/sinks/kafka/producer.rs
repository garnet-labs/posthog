use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll};
use std::time::Duration;

use rdkafka::error::{KafkaError, RDKafkaErrorCode};
use rdkafka::message::OwnedHeaders;
use rdkafka::producer::{DeliveryFuture, FutureProducer, FutureRecord, Producer};
use rdkafka::ClientConfig;
use tracing::{info, warn};

use common_types::CapturedEventHeaders;

use crate::config::{ClusterName, V1KafkaClusterConfig};
use crate::v1::sinks::kafka::context::{KafkaContext, ProducerHealth};

// ---------------------------------------------------------------------------
// ProduceError
// ---------------------------------------------------------------------------

#[derive(Debug, thiserror::Error)]
pub enum ProduceError {
    #[error("event too big: {message}")]
    EventTooBig { message: String },

    #[error("kafka error: {source}")]
    Kafka {
        #[source]
        source: KafkaError,
        code: Option<RDKafkaErrorCode>,
        retriable: bool,
    },

    #[error("delivery cancelled (timeout in librdkafka)")]
    DeliveryCancelled,
}

impl ProduceError {
    pub fn is_retriable(&self) -> bool {
        match self {
            Self::EventTooBig { .. } => false,
            Self::Kafka { retriable, .. } => *retriable,
            Self::DeliveryCancelled => true,
        }
    }

    pub fn kafka_error(&self) -> Option<&KafkaError> {
        match self {
            Self::Kafka { source, .. } => Some(source),
            _ => None,
        }
    }

    pub fn error_code(&self) -> Option<RDKafkaErrorCode> {
        match self {
            Self::Kafka { code, .. } => *code,
            _ => None,
        }
    }
}

// ---------------------------------------------------------------------------
// ProduceRecord
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct ProduceRecord {
    pub topic: String,
    pub key: Option<String>,
    pub payload: String,
    pub headers: CapturedEventHeaders,
}

// ---------------------------------------------------------------------------
// SendHandle
// ---------------------------------------------------------------------------

pub struct SendHandle {
    inner: DeliveryFuture,
}

impl Future for SendHandle {
    type Output = Result<(), ProduceError>;

    fn poll(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        match Pin::new(&mut self.inner).poll(cx) {
            Poll::Pending => Poll::Pending,
            Poll::Ready(Err(_)) => Poll::Ready(Err(ProduceError::DeliveryCancelled)),
            Poll::Ready(Ok(Err((e, _)))) => Poll::Ready(Err(produce_error_from_kafka(e))),
            Poll::Ready(Ok(Ok(_))) => Poll::Ready(Ok(())),
        }
    }
}

// ---------------------------------------------------------------------------
// KafkaProducer
// ---------------------------------------------------------------------------

pub struct KafkaProducer {
    inner: FutureProducer<KafkaContext>,
    health: Arc<ProducerHealth>,
    cluster: ClusterName,
}

impl KafkaProducer {
    pub fn new(
        cluster: ClusterName,
        config: &V1KafkaClusterConfig,
        handle: lifecycle::Handle,
        capture_mode: &'static str,
    ) -> anyhow::Result<Self> {
        let health = Arc::new(ProducerHealth::new());
        let ctx = KafkaContext::new(handle, health.clone(), cluster, capture_mode);

        let mut client_config = ClientConfig::new();
        client_config
            .set("bootstrap.servers", &config.hosts)
            .set("statistics.interval.ms", "10000")
            .set("linger.ms", config.linger_ms.to_string())
            .set("message.timeout.ms", config.message_timeout_ms.to_string())
            .set("message.max.bytes", config.message_max_bytes.to_string())
            .set("compression.codec", &config.compression_codec)
            .set(
                "queue.buffering.max.kbytes",
                (config.queue_mib * 1024).to_string(),
            )
            .set("acks", &config.acks)
            .set("batch.num.messages", config.batch_num_messages.to_string())
            .set("batch.size", config.batch_size.to_string())
            .set("enable.idempotence", config.enable_idempotence.to_string());

        if !config.client_id.is_empty() {
            client_config.set("client.id", &config.client_id);
        }
        if config.tls {
            client_config
                .set("security.protocol", "ssl")
                .set("enable.ssl.certificate.verification", "false");
        }

        let producer: FutureProducer<KafkaContext> = client_config.create_with_context(ctx)?;

        match producer
            .client()
            .fetch_metadata(None, Duration::from_secs(10))
        {
            Ok(_) => {
                health.set_ready(true);
                info!("v1 kafka producer [{}] connected", cluster.as_str());
            }
            Err(e) => {
                warn!(
                    "v1 kafka producer [{}]: initial metadata fetch failed: {e}",
                    cluster.as_str()
                );
            }
        }

        Ok(Self {
            inner: producer,
            health,
            cluster,
        })
    }
}

impl super::KafkaProducerTrait for KafkaProducer {
    type Ack = SendHandle;

    fn send(&self, record: ProduceRecord) -> Result<SendHandle, ProduceError> {
        let headers: OwnedHeaders = record.headers.into();
        match self.inner.send_result(FutureRecord {
            topic: &record.topic,
            payload: Some(&record.payload),
            partition: None,
            key: record.key.as_deref(),
            timestamp: None,
            headers: Some(headers),
        }) {
            Ok(future) => Ok(SendHandle { inner: future }),
            Err((e, _)) => Err(produce_error_from_kafka(e)),
        }
    }

    fn flush(&self, timeout: Duration) -> Result<(), KafkaError> {
        self.inner.flush(rdkafka::util::Timeout::After(timeout))
    }

    fn health(&self) -> &Arc<ProducerHealth> {
        &self.health
    }

    fn cluster_name(&self) -> ClusterName {
        self.cluster
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn is_fatal_kafka_error(e: &KafkaError) -> bool {
    matches!(
        e.rdkafka_error_code(),
        Some(
            RDKafkaErrorCode::MessageSizeTooLarge
                | RDKafkaErrorCode::InvalidMessageSize
                | RDKafkaErrorCode::InvalidMessage
                | RDKafkaErrorCode::TopicAuthorizationFailed
                | RDKafkaErrorCode::ClusterAuthorizationFailed
        )
    )
}

pub(crate) fn produce_error_from_kafka(e: KafkaError) -> ProduceError {
    let code = e.rdkafka_error_code();
    if code == Some(RDKafkaErrorCode::MessageSizeTooLarge) {
        ProduceError::EventTooBig {
            message: e.to_string(),
        }
    } else {
        ProduceError::Kafka {
            retriable: !is_fatal_kafka_error(&e),
            code,
            source: e,
        }
    }
}
