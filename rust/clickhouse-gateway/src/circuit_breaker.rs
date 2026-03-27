use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::RwLock;
use std::time::{Duration, Instant};

use tracing::{info, warn};

use crate::error::GatewayError;

/// Circuit breaker states following the standard pattern:
/// - Closed: requests flow normally, failures are tracked
/// - Open: requests are rejected immediately to protect ClickHouse
/// - HalfOpen: a single probe request is allowed through to test recovery
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CircuitState {
    /// Normal operation — requests pass through, failures are counted.
    Closed,
    /// Circuit is tripped — all requests are rejected until cooldown expires.
    Open,
    /// Cooldown expired — one probe request is allowed to test if the backend recovered.
    HalfOpen,
}

impl std::fmt::Display for CircuitState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CircuitState::Closed => write!(f, "CLOSED"),
            CircuitState::Open => write!(f, "OPEN"),
            CircuitState::HalfOpen => write!(f, "HALF_OPEN"),
        }
    }
}

/// Configuration for a single circuit breaker instance.
#[derive(Debug, Clone)]
pub struct CircuitBreakerConfig {
    /// Percentage of failures (0.0–100.0) that triggers the circuit to open.
    pub error_threshold_percent: f64,
    /// Sliding window duration in seconds for counting successes and failures.
    pub window_seconds: u64,
    /// Minimum number of requests in the window before the threshold is evaluated.
    /// Prevents the circuit from tripping on a single failure at startup.
    pub minimum_requests: u64,
    /// How long to wait in the Open state before transitioning to HalfOpen.
    pub cooldown: Duration,
    /// Human-readable name for this breaker (used in logs and metrics).
    pub workload_name: String,
}

impl Default for CircuitBreakerConfig {
    fn default() -> Self {
        Self {
            error_threshold_percent: 50.0,
            window_seconds: 30,
            minimum_requests: 10,
            cooldown: Duration::from_secs(60),
            workload_name: "unknown".to_string(),
        }
    }
}

/// Per-workload circuit breaker.
///
/// Uses `std::sync` primitives (atomics + RwLock) for the fast path — the check
/// in the Closed state only reads an atomic, no lock acquisition needed for the
/// common case. The RwLock is only contended during state transitions.
pub struct CircuitBreaker {
    state: RwLock<CircuitState>,
    /// Total failures recorded in the current window.
    failure_count: AtomicU64,
    /// Total successes recorded in the current window.
    success_count: AtomicU64,
    /// Timestamp of the last failure — used to determine cooldown expiry.
    last_failure_time: RwLock<Option<Instant>>,
    /// Timestamp when the current counting window started.
    window_start: RwLock<Instant>,
    /// Guard that allows exactly one probe request through in HalfOpen state.
    /// Set to `true` when a probe is in-flight; cleared on success/failure.
    half_open_probe_active: AtomicBool,
    config: CircuitBreakerConfig,
}

impl CircuitBreaker {
    pub fn new(config: CircuitBreakerConfig) -> Self {
        Self {
            state: RwLock::new(CircuitState::Closed),
            failure_count: AtomicU64::new(0),
            success_count: AtomicU64::new(0),
            last_failure_time: RwLock::new(None),
            window_start: RwLock::new(Instant::now()),
            half_open_probe_active: AtomicBool::new(false),
            config,
        }
    }

    /// Returns the current circuit state.
    pub fn state(&self) -> CircuitState {
        *self
            .state
            .read()
            .expect("circuit breaker state lock poisoned")
    }

    /// Check whether a request should be allowed through.
    ///
    /// - **Closed**: always allows.
    /// - **Open**: rejects unless the cooldown has elapsed, in which case it
    ///   transitions to HalfOpen and allows the probe.
    /// - **HalfOpen**: allows (the single probe request).
    pub fn check(&self) -> Result<(), GatewayError> {
        let current_state = self.state();

        match current_state {
            CircuitState::Closed => Ok(()),
            CircuitState::Open => {
                // Check whether cooldown has elapsed
                if self.cooldown_elapsed() {
                    // Try to claim the single probe slot
                    if self
                        .half_open_probe_active
                        .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
                        .is_ok()
                    {
                        self.transition_to(CircuitState::HalfOpen);
                        Ok(())
                    } else {
                        // Another request already claimed the probe
                        let workload = &self.config.workload_name;
                        Err(GatewayError::CircuitBreakerOpen(workload.clone()))
                    }
                } else {
                    let workload = &self.config.workload_name;
                    warn!(
                        workload = %workload,
                        "circuit breaker open, rejecting request"
                    );
                    metrics::counter!(
                        "gateway_circuit_breaker_rejected_total",
                        "workload" => workload.clone()
                    )
                    .increment(1);
                    Err(GatewayError::CircuitBreakerOpen(workload.clone()))
                }
            }
            CircuitState::HalfOpen => {
                // Only the single probe request is allowed; others are rejected
                if self.half_open_probe_active.load(Ordering::Acquire) {
                    let workload = &self.config.workload_name;
                    Err(GatewayError::CircuitBreakerOpen(workload.clone()))
                } else {
                    // Shouldn't happen — HalfOpen without active probe means
                    // the probe completed but state hasn't transitioned yet.
                    Ok(())
                }
            }
        }
    }

    /// Record a successful request. In HalfOpen state this closes the circuit.
    pub fn record_success(&self) {
        self.maybe_reset_window();
        self.success_count.fetch_add(1, Ordering::Relaxed);

        let current_state = self.state();
        if current_state == CircuitState::HalfOpen {
            info!(
                workload = %self.config.workload_name,
                "circuit breaker probe succeeded, closing circuit"
            );
            self.half_open_probe_active.store(false, Ordering::Release);
            self.transition_to(CircuitState::Closed);
            self.reset_counters();
        }
    }

    /// Record a failed request. If the failure rate exceeds the threshold,
    /// the circuit transitions from Closed to Open (or HalfOpen back to Open).
    pub fn record_failure(&self) {
        self.maybe_reset_window();
        self.failure_count.fetch_add(1, Ordering::Relaxed);

        // Update last failure time
        {
            let mut last = self
                .last_failure_time
                .write()
                .expect("last_failure_time lock poisoned");
            *last = Some(Instant::now());
        }

        let current_state = self.state();

        match current_state {
            CircuitState::HalfOpen => {
                // Probe failed — reopen immediately
                warn!(
                    workload = %self.config.workload_name,
                    "circuit breaker probe failed, reopening circuit"
                );
                self.half_open_probe_active.store(false, Ordering::Release);
                self.transition_to(CircuitState::Open);
            }
            CircuitState::Closed => {
                if self.threshold_exceeded() {
                    let failures = self.failure_count.load(Ordering::Relaxed);
                    let successes = self.success_count.load(Ordering::Relaxed);
                    let total = failures + successes;
                    let rate = if total > 0 {
                        (failures as f64 / total as f64) * 100.0
                    } else {
                        0.0
                    };
                    warn!(
                        workload = %self.config.workload_name,
                        failures,
                        total,
                        error_rate = format!("{:.1}%", rate),
                        threshold = format!("{:.1}%", self.config.error_threshold_percent),
                        "circuit breaker tripped, opening circuit"
                    );
                    self.transition_to(CircuitState::Open);
                }
            }
            CircuitState::Open => {
                // Already open, nothing to do
            }
        }
    }

    /// Returns the current failure count (useful for tests and metrics).
    pub fn failure_count(&self) -> u64 {
        self.failure_count.load(Ordering::Relaxed)
    }

    /// Returns the current success count (useful for tests and metrics).
    pub fn success_count(&self) -> u64 {
        self.success_count.load(Ordering::Relaxed)
    }

    /// Returns the configured workload name.
    pub fn workload_name(&self) -> &str {
        &self.config.workload_name
    }

    // -- Private helpers --

    /// Check whether the error threshold has been exceeded within the current window.
    fn threshold_exceeded(&self) -> bool {
        let failures = self.failure_count.load(Ordering::Relaxed);
        let successes = self.success_count.load(Ordering::Relaxed);
        let total = failures + successes;

        // Don't trip on too few samples
        if total < self.config.minimum_requests {
            return false;
        }

        let error_rate = (failures as f64 / total as f64) * 100.0;
        error_rate >= self.config.error_threshold_percent
    }

    /// Check whether the cooldown period has elapsed since the last failure.
    fn cooldown_elapsed(&self) -> bool {
        let last = self
            .last_failure_time
            .read()
            .expect("last_failure_time lock poisoned");
        match *last {
            Some(t) => t.elapsed() >= self.config.cooldown,
            // No failure recorded — shouldn't be Open, but allow transition
            None => true,
        }
    }

    /// If the current counting window has expired, reset the counters.
    fn maybe_reset_window(&self) {
        let window_duration = Duration::from_secs(self.config.window_seconds);
        let should_reset = {
            let start = self
                .window_start
                .read()
                .expect("window_start lock poisoned");
            start.elapsed() >= window_duration
        };

        if should_reset {
            let mut start = self
                .window_start
                .write()
                .expect("window_start lock poisoned");
            // Double-check after acquiring write lock to avoid thundering herd reset
            if start.elapsed() >= window_duration {
                *start = Instant::now();
                self.reset_counters();
            }
        }
    }

    /// Reset success and failure counters to zero.
    fn reset_counters(&self) {
        self.failure_count.store(0, Ordering::Relaxed);
        self.success_count.store(0, Ordering::Relaxed);
    }

    /// Transition to a new state, emitting a metric.
    fn transition_to(&self, new_state: CircuitState) {
        let mut state = self
            .state
            .write()
            .expect("circuit breaker state lock poisoned");
        let old_state = *state;
        *state = new_state;

        info!(
            workload = %self.config.workload_name,
            from = %old_state,
            to = %new_state,
            "circuit breaker state transition"
        );

        metrics::counter!(
            "gateway_circuit_breaker_transitions_total",
            "workload" => self.config.workload_name.clone(),
            "from" => old_state.to_string(),
            "to" => new_state.to_string()
        )
        .increment(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> CircuitBreakerConfig {
        CircuitBreakerConfig {
            error_threshold_percent: 50.0,
            window_seconds: 30,
            minimum_requests: 4,
            cooldown: Duration::from_millis(50),
            workload_name: "TEST".to_string(),
        }
    }

    #[test]
    fn test_initial_state_is_closed() {
        let cb = CircuitBreaker::new(test_config());
        assert_eq!(cb.state(), CircuitState::Closed);
    }

    #[test]
    fn test_closed_allows_requests() {
        let cb = CircuitBreaker::new(test_config());
        assert!(cb.check().is_ok());
    }

    #[test]
    fn test_does_not_trip_below_minimum_requests() {
        let cb = CircuitBreaker::new(test_config());
        // 3 failures out of 3 total, but minimum_requests is 4
        for _ in 0..3 {
            cb.record_failure();
        }
        assert_eq!(cb.state(), CircuitState::Closed);
        assert!(cb.check().is_ok());
    }

    #[test]
    fn test_trips_at_threshold() {
        let cb = CircuitBreaker::new(test_config());
        // 2 successes + 2 failures = 50% error rate, threshold is 50%
        cb.record_success();
        cb.record_success();
        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);
    }

    #[test]
    fn test_open_rejects_requests() {
        let config = CircuitBreakerConfig {
            cooldown: Duration::from_secs(3600), // very long cooldown
            ..test_config()
        };
        let cb = CircuitBreaker::new(config);
        // Trip the circuit
        cb.record_success();
        cb.record_success();
        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);

        let result = cb.check();
        assert!(result.is_err());
        match result.unwrap_err() {
            GatewayError::CircuitBreakerOpen(w) => assert_eq!(w, "TEST"),
            other => panic!("expected CircuitBreakerOpen, got: {other:?}"),
        }
    }

    #[test]
    fn test_half_open_after_cooldown() {
        let cb = CircuitBreaker::new(test_config()); // 50ms cooldown
                                                     // Trip the circuit
        cb.record_success();
        cb.record_success();
        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);

        // Wait for cooldown
        std::thread::sleep(Duration::from_millis(60));

        // check() should transition to HalfOpen and allow
        assert!(cb.check().is_ok());
        assert_eq!(cb.state(), CircuitState::HalfOpen);
    }

    #[test]
    fn test_half_open_closes_on_success() {
        let cb = CircuitBreaker::new(test_config());
        // Trip the circuit
        cb.record_success();
        cb.record_success();
        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);

        // Wait for cooldown and transition to HalfOpen
        std::thread::sleep(Duration::from_millis(60));
        assert!(cb.check().is_ok());
        assert_eq!(cb.state(), CircuitState::HalfOpen);

        // Probe succeeds
        cb.record_success();
        assert_eq!(cb.state(), CircuitState::Closed);
    }

    #[test]
    fn test_half_open_reopens_on_failure() {
        let cb = CircuitBreaker::new(test_config());
        // Trip the circuit
        cb.record_success();
        cb.record_success();
        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);

        // Wait for cooldown and transition to HalfOpen
        std::thread::sleep(Duration::from_millis(60));
        assert!(cb.check().is_ok());
        assert_eq!(cb.state(), CircuitState::HalfOpen);

        // Probe fails
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);
    }

    #[test]
    fn test_success_resets_failure_count() {
        let cb = CircuitBreaker::new(test_config());
        // Trip the circuit
        cb.record_success();
        cb.record_success();
        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);

        // Recover via HalfOpen -> Closed
        std::thread::sleep(Duration::from_millis(60));
        assert!(cb.check().is_ok());
        cb.record_success();
        assert_eq!(cb.state(), CircuitState::Closed);

        // Counters should be reset
        assert_eq!(cb.failure_count(), 0);
        assert_eq!(cb.success_count(), 0);
    }

    #[test]
    fn test_stays_closed_below_threshold() {
        let cb = CircuitBreaker::new(test_config());
        // 9 successes + 1 failure = 10% error rate, well below 50%
        for _ in 0..9 {
            cb.record_success();
        }
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Closed);
    }

    #[test]
    fn test_display_circuit_state() {
        assert_eq!(CircuitState::Closed.to_string(), "CLOSED");
        assert_eq!(CircuitState::Open.to_string(), "OPEN");
        assert_eq!(CircuitState::HalfOpen.to_string(), "HALF_OPEN");
    }
}
