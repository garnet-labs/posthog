use std::sync::Arc;

use crate::cache::QueryCache;
use crate::circuit_breaker_registry::CircuitBreakerRegistry;
use crate::config::Config;
use crate::routing::WorkloadRouter;
use crate::scheduling::Scheduler;
use crate::team_limits::TeamLimits;

/// Shared application state accessible from all handlers.
#[derive(Clone)]
pub struct AppState {
    pub config: Arc<Config>,
    pub router: Arc<WorkloadRouter>,
    pub scheduler: Arc<Scheduler>,
    pub team_limits: Arc<TeamLimits>,
    pub circuit_breakers: Arc<CircuitBreakerRegistry>,
    pub cache: Arc<QueryCache>,
    pub http_client: reqwest::Client,
}

impl AppState {
    pub fn new(config: Config) -> Self {
        let router = WorkloadRouter::from_config(&config);
        let scheduler = Scheduler::new(&config);
        let team_limits = TeamLimits::new(&config);
        let circuit_breakers = CircuitBreakerRegistry::new(&config);
        let cache = QueryCache::new(config.redis_url.as_deref());
        let http_client = reqwest::Client::builder()
            .pool_max_idle_per_host(10)
            .timeout(std::time::Duration::from_secs(
                config.offline_max_execution_time as u64 + 5,
            ))
            .build()
            .expect("failed to build HTTP client");

        Self {
            config: Arc::new(config),
            router: Arc::new(router),
            scheduler: Arc::new(scheduler),
            team_limits: Arc::new(team_limits),
            circuit_breakers: Arc::new(circuit_breakers),
            cache: Arc::new(cache),
            http_client,
        }
    }
}
