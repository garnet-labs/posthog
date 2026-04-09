use std::net::SocketAddr;

use envconfig::Envconfig;

#[derive(Envconfig, Clone, Debug)]
pub struct Config {
    #[envconfig(from = "ADDRESS", default = "0.0.0.0:3002")]
    pub address: SocketAddr,

    #[envconfig(from = "REDIS_URL", default = "redis://localhost:6379/")]
    pub redis_url: String,

    /// Optional: separate URL for Redis read replicas.
    /// Falls back to REDIS_URL if not set.
    #[envconfig(from = "REDIS_READER_URL", default = "")]
    pub redis_reader_url: String,

    #[envconfig(from = "REDIS_TIMEOUT_MS", default = "100")]
    pub redis_timeout_ms: u64,

    #[envconfig(from = "OBJECT_STORAGE_REGION", default = "us-east-1")]
    pub object_storage_region: String,

    #[envconfig(from = "OBJECT_STORAGE_BUCKET", default = "posthog")]
    pub object_storage_bucket: String,

    #[envconfig(from = "OBJECT_STORAGE_ENDPOINT", default = "")]
    pub object_storage_endpoint: String,

    #[envconfig(from = "ENABLE_METRICS", default = "false")]
    pub enable_metrics: bool,

    #[envconfig(from = "DEBUG", default = "false")]
    pub debug: bool,

    #[envconfig(from = "MAX_CONCURRENCY", default = "1000")]
    pub max_concurrency: usize,
}
