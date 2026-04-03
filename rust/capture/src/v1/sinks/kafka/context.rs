use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use metrics::{counter, gauge};

use crate::config::ClusterName;

// ---------------------------------------------------------------------------
// ProducerHealth
// ---------------------------------------------------------------------------

pub struct ProducerHealth {
    any_broker_up: AtomicBool,
}

impl Default for ProducerHealth {
    fn default() -> Self {
        Self::new()
    }
}

impl ProducerHealth {
    pub fn new() -> Self {
        Self {
            any_broker_up: AtomicBool::new(false),
        }
    }

    pub fn is_ready(&self) -> bool {
        self.any_broker_up.load(Ordering::Relaxed)
    }

    pub fn set_ready(&self, ready: bool) {
        self.any_broker_up.store(ready, Ordering::Relaxed);
    }
}

// ---------------------------------------------------------------------------
// KafkaContext
// ---------------------------------------------------------------------------

pub(crate) struct KafkaContext {
    handle: lifecycle::Handle,
    health: Arc<ProducerHealth>,
    cluster: ClusterName,
    mode: &'static str,
}

impl KafkaContext {
    pub fn new(
        handle: lifecycle::Handle,
        health: Arc<ProducerHealth>,
        cluster: ClusterName,
        mode: &'static str,
    ) -> Self {
        Self {
            handle,
            health,
            cluster,
            mode,
        }
    }
}

impl rdkafka::ClientContext for KafkaContext {
    fn stats(&self, stats: rdkafka::Statistics) {
        let cluster = self.cluster.as_str();
        let mode = self.mode;

        let brokers_up = stats.brokers.values().any(|b| b.state == "UP");
        self.health.set_ready(brokers_up);
        if brokers_up {
            self.handle.report_healthy();
        }

        gauge!("capture_v1_kafka_producer_queue_depth",
            "cluster" => cluster, "mode" => mode)
        .set(stats.msg_cnt as f64);
        gauge!("capture_v1_kafka_producer_queue_bytes",
            "cluster" => cluster, "mode" => mode)
        .set(stats.msg_size as f64);

        for (topic, ts) in &stats.topics {
            gauge!("capture_v1_kafka_batch_size_bytes_avg",
                "cluster" => cluster, "mode" => mode, "topic" => topic.clone())
            .set(ts.batchsize.avg as f64);
        }

        for bs in stats.brokers.values() {
            let id = bs.nodeid.to_string();
            gauge!("capture_v1_kafka_broker_connected",
                "cluster" => cluster, "mode" => mode, "broker" => id.clone())
            .set(if bs.state == "UP" { 1.0 } else { 0.0 });
            if let Some(rtt) = &bs.rtt {
                gauge!("capture_v1_kafka_broker_rtt_us",
                    "cluster" => cluster, "mode" => mode,
                    "quantile" => "p50", "broker" => id.clone())
                .set(rtt.p50 as f64);
                gauge!("capture_v1_kafka_broker_rtt_us",
                    "cluster" => cluster, "mode" => mode,
                    "quantile" => "p99", "broker" => id.clone())
                .set(rtt.p99 as f64);
            }
            counter!("capture_v1_kafka_broker_tx_errors_total",
                "cluster" => cluster, "mode" => mode, "broker" => id.clone())
            .absolute(bs.txerrs);
            counter!("capture_v1_kafka_broker_rx_errors_total",
                "cluster" => cluster, "mode" => mode, "broker" => id.clone())
            .absolute(bs.rxerrs);
        }
    }
}
