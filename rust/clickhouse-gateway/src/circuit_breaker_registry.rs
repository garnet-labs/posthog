use std::collections::HashMap;
use std::time::Duration;

use crate::circuit_breaker::{CircuitBreaker, CircuitBreakerConfig};
use crate::config::Config;
use crate::routing::Workload;

/// Default error threshold percentage for all workloads.
const DEFAULT_ERROR_THRESHOLD_PERCENT: f64 = 50.0;

/// Default sliding window duration in seconds.
const DEFAULT_WINDOW_SECONDS: u64 = 30;

/// Default minimum requests before evaluating threshold.
const DEFAULT_MINIMUM_REQUESTS: u64 = 10;

/// Cooldown for latency-sensitive workloads (ONLINE, ENDPOINTS, LOGS, DEFAULT).
const ONLINE_COOLDOWN_SECS: u64 = 60;

/// Cooldown for batch workloads (OFFLINE) — longer because these are less urgent.
const OFFLINE_COOLDOWN_SECS: u64 = 120;

/// Holds one [`CircuitBreaker`] per workload type.
///
/// Created once at startup and shared via `Arc` in [`AppState`]. Each workload
/// has its own independent failure tracking and cooldown duration.
pub struct CircuitBreakerRegistry {
    breakers: HashMap<String, CircuitBreaker>,
}

impl CircuitBreakerRegistry {
    /// Build a registry from the gateway config, creating one breaker per known workload.
    pub fn new(_config: &Config) -> Self {
        let workloads = [
            Workload::Online,
            Workload::Offline,
            Workload::Logs,
            Workload::Endpoints,
            Workload::Default,
        ];

        let mut breakers = HashMap::new();

        for workload in workloads {
            let name = workload.as_str().to_string();
            let cooldown = cooldown_for_workload(&workload);
            let config = CircuitBreakerConfig {
                error_threshold_percent: DEFAULT_ERROR_THRESHOLD_PERCENT,
                window_seconds: DEFAULT_WINDOW_SECONDS,
                minimum_requests: DEFAULT_MINIMUM_REQUESTS,
                cooldown,
                workload_name: name.clone(),
            };
            breakers.insert(name, CircuitBreaker::new(config));
        }

        Self { breakers }
    }

    /// Get the circuit breaker for a workload by its string key (e.g. "ONLINE").
    ///
    /// Panics if the workload is not in the registry — this is a programming error
    /// since the registry is initialized with all known workloads at startup.
    pub fn get(&self, workload: &str) -> &CircuitBreaker {
        self.breakers
            .get(workload)
            .unwrap_or_else(|| panic!("no circuit breaker registered for workload: {workload}"))
    }

    /// Returns an iterator over all registered breakers (useful for health/status endpoints).
    pub fn iter(&self) -> impl Iterator<Item = (&String, &CircuitBreaker)> {
        self.breakers.iter()
    }
}

/// Returns the appropriate cooldown duration for a workload.
fn cooldown_for_workload(workload: &Workload) -> Duration {
    match workload {
        Workload::Offline => Duration::from_secs(OFFLINE_COOLDOWN_SECS),
        _ => Duration::from_secs(ONLINE_COOLDOWN_SECS),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> Config {
        crate::config::test_config()
    }

    #[test]
    fn test_registry_has_all_workloads() {
        let registry = CircuitBreakerRegistry::new(&test_config());
        // Should not panic for any known workload
        let _ = registry.get("ONLINE");
        let _ = registry.get("OFFLINE");
        let _ = registry.get("LOGS");
        let _ = registry.get("ENDPOINTS");
        let _ = registry.get("DEFAULT");
    }

    #[test]
    #[should_panic(expected = "no circuit breaker registered for workload: BOGUS")]
    fn test_registry_panics_on_unknown_workload() {
        let registry = CircuitBreakerRegistry::new(&test_config());
        let _ = registry.get("BOGUS");
    }

    #[test]
    fn test_offline_has_longer_cooldown() {
        assert_eq!(
            cooldown_for_workload(&Workload::Offline),
            Duration::from_secs(OFFLINE_COOLDOWN_SECS)
        );
        assert_eq!(
            cooldown_for_workload(&Workload::Online),
            Duration::from_secs(ONLINE_COOLDOWN_SECS)
        );
        // Verify offline cooldown is strictly longer than online
        assert!(
            cooldown_for_workload(&Workload::Offline) > cooldown_for_workload(&Workload::Online)
        );
    }

    #[test]
    fn test_per_workload_isolation() {
        let registry = CircuitBreakerRegistry::new(&test_config());
        let online = registry.get("ONLINE");
        let offline = registry.get("OFFLINE");

        // Record failures on ONLINE only
        for _ in 0..20 {
            online.record_failure();
        }

        // OFFLINE should still be closed
        assert!(offline.check().is_ok());
        assert_eq!(
            offline.state(),
            crate::circuit_breaker::CircuitState::Closed
        );
    }
}
