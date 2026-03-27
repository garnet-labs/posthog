use std::time::Duration;

use clickhouse_gateway::circuit_breaker::{CircuitBreaker, CircuitBreakerConfig, CircuitState};
use clickhouse_gateway::circuit_breaker_registry::CircuitBreakerRegistry;
use clickhouse_gateway::config::Config;
use clickhouse_gateway::error::GatewayError;

fn make_config(cooldown_ms: u64) -> CircuitBreakerConfig {
    CircuitBreakerConfig {
        error_threshold_percent: 50.0,
        window_seconds: 60,
        minimum_requests: 4,
        cooldown: Duration::from_millis(cooldown_ms),
        workload_name: "TEST".to_string(),
    }
}

fn make_gateway_config() -> Config {
    Config {
        host: "0.0.0.0".to_string(),
        port: 3100,
        clickhouse_online_hosts: "http://localhost:8123".to_string(),
        clickhouse_offline_hosts: "http://localhost:8123".to_string(),
        clickhouse_logs_hosts: "http://localhost:8123".to_string(),
        clickhouse_endpoints_hosts: "http://localhost:8123".to_string(),
        online_max_concurrent: 50,
        online_max_execution_time: 30,
        offline_max_concurrent: 10,
        offline_max_execution_time: 600,
        logs_max_concurrent: 20,
        logs_max_execution_time: 60,
        endpoints_max_concurrent: 30,
        endpoints_max_execution_time: 120,
        service_token: String::new(),
        auth_disabled: true,
        redis_url: None,
        explain_enabled: true,
        metrics_port: 9090,
        log_level: "info".to_string(),
    }
}

// -- Basic state tests --

#[test]
fn test_closed_allows_requests() {
    let cb = CircuitBreaker::new(make_config(5000));
    assert_eq!(cb.state(), CircuitState::Closed);
    assert!(cb.check().is_ok());
    // Multiple checks should all pass
    for _ in 0..100 {
        assert!(cb.check().is_ok());
    }
}

#[test]
fn test_open_rejects_requests() {
    let cb = CircuitBreaker::new(make_config(60_000)); // long cooldown
                                                       // Trip the breaker: 2 successes + 2 failures = 50% error rate at minimum_requests=4
    cb.record_success();
    cb.record_success();
    cb.record_failure();
    cb.record_failure();

    assert_eq!(cb.state(), CircuitState::Open);

    let result = cb.check();
    assert!(result.is_err());
    match result.unwrap_err() {
        GatewayError::CircuitBreakerOpen(name) => assert_eq!(name, "TEST"),
        other => panic!("expected CircuitBreakerOpen, got: {other:?}"),
    }
}

#[test]
fn test_transitions_to_open_on_threshold() {
    let cb = CircuitBreaker::new(make_config(5000));

    // Below minimum_requests — should stay closed
    cb.record_failure();
    cb.record_failure();
    cb.record_failure();
    assert_eq!(cb.state(), CircuitState::Closed);

    // 4th request (1 success + 3 failures prior isn't enough... let's be explicit)
    // Reset: new breaker for clean counting
    let cb = CircuitBreaker::new(make_config(5000));

    // 3 successes, 1 failure = 25% error rate, below 50%
    cb.record_success();
    cb.record_success();
    cb.record_success();
    cb.record_failure();
    assert_eq!(cb.state(), CircuitState::Closed);

    // Now push to exactly 50%: 2 successes + 2 failures
    let cb = CircuitBreaker::new(make_config(5000));
    cb.record_success();
    cb.record_success();
    cb.record_failure();
    // At this point: 2S + 1F = 33%, still Closed, and total=3 < minimum_requests=4
    assert_eq!(cb.state(), CircuitState::Closed);
    cb.record_failure();
    // Now: 2S + 2F = 50%, total=4 >= minimum_requests=4 -> should trip
    assert_eq!(cb.state(), CircuitState::Open);
}

#[test]
fn test_half_open_after_cooldown() {
    let cb = CircuitBreaker::new(make_config(50)); // 50ms cooldown

    // Trip the breaker
    cb.record_success();
    cb.record_success();
    cb.record_failure();
    cb.record_failure();
    assert_eq!(cb.state(), CircuitState::Open);

    // Before cooldown: still rejects
    let result = cb.check();
    // Might already be past cooldown on a slow machine, so just check state transitions work
    if result.is_err() {
        // Wait for cooldown
        std::thread::sleep(Duration::from_millis(60));
    }

    // After cooldown: should transition to HalfOpen
    let result = cb.check();
    assert!(result.is_ok());
    assert_eq!(cb.state(), CircuitState::HalfOpen);
}

#[test]
fn test_half_open_closes_on_success() {
    let cb = CircuitBreaker::new(make_config(50));

    // Trip and wait
    cb.record_success();
    cb.record_success();
    cb.record_failure();
    cb.record_failure();
    assert_eq!(cb.state(), CircuitState::Open);
    std::thread::sleep(Duration::from_millis(60));

    // Transition to HalfOpen
    assert!(cb.check().is_ok());
    assert_eq!(cb.state(), CircuitState::HalfOpen);

    // Successful probe closes the circuit
    cb.record_success();
    assert_eq!(cb.state(), CircuitState::Closed);

    // Should allow requests again
    assert!(cb.check().is_ok());
}

#[test]
fn test_half_open_reopens_on_failure() {
    let cb = CircuitBreaker::new(make_config(50));

    // Trip and wait
    cb.record_success();
    cb.record_success();
    cb.record_failure();
    cb.record_failure();
    assert_eq!(cb.state(), CircuitState::Open);
    std::thread::sleep(Duration::from_millis(60));

    // Transition to HalfOpen
    assert!(cb.check().is_ok());
    assert_eq!(cb.state(), CircuitState::HalfOpen);

    // Failed probe reopens the circuit
    cb.record_failure();
    assert_eq!(cb.state(), CircuitState::Open);
}

#[test]
fn test_per_workload_isolation() {
    let registry = CircuitBreakerRegistry::new(&make_gateway_config());

    let online = registry.get("ONLINE");
    let offline = registry.get("OFFLINE");
    let logs = registry.get("LOGS");

    // Hammer ONLINE with failures — should not affect OFFLINE or LOGS
    for _ in 0..20 {
        online.record_failure();
    }

    // ONLINE is open (20 failures > minimum_requests, 100% error rate)
    assert_eq!(online.state(), CircuitState::Open);

    // OFFLINE and LOGS remain closed
    assert_eq!(offline.state(), CircuitState::Closed);
    assert!(offline.check().is_ok());
    assert_eq!(logs.state(), CircuitState::Closed);
    assert!(logs.check().is_ok());
}

#[test]
fn test_success_resets_failure_count() {
    let cb = CircuitBreaker::new(make_config(50));

    // Trip the breaker
    cb.record_success();
    cb.record_success();
    cb.record_failure();
    cb.record_failure();
    assert_eq!(cb.state(), CircuitState::Open);

    // Recover
    std::thread::sleep(Duration::from_millis(60));
    assert!(cb.check().is_ok()); // -> HalfOpen
    cb.record_success(); // -> Closed

    // Counters should be reset
    assert_eq!(cb.failure_count(), 0);
    assert_eq!(cb.success_count(), 0);

    // Should be able to handle requests normally again
    assert_eq!(cb.state(), CircuitState::Closed);
    assert!(cb.check().is_ok());
}

// -- Registry tests --

#[test]
fn test_registry_all_workloads_present() {
    let registry = CircuitBreakerRegistry::new(&make_gateway_config());
    for wl in &["ONLINE", "OFFLINE", "LOGS", "ENDPOINTS", "DEFAULT"] {
        let breaker = registry.get(wl);
        assert_eq!(breaker.state(), CircuitState::Closed);
        assert_eq!(breaker.workload_name(), *wl);
    }
}

#[test]
#[should_panic(expected = "no circuit breaker registered for workload: NONEXISTENT")]
fn test_registry_panics_on_unknown() {
    let registry = CircuitBreakerRegistry::new(&make_gateway_config());
    let _ = registry.get("NONEXISTENT");
}

// -- Error type tests --

#[test]
fn test_circuit_breaker_error_type() {
    let err = GatewayError::CircuitBreakerOpen("ONLINE".to_string());
    assert_eq!(err.error_type(), "circuit_breaker_open");
    assert_eq!(
        err.status_code(),
        axum::http::StatusCode::SERVICE_UNAVAILABLE
    );
    assert!(err.to_string().contains("ONLINE"));
}

// -- Full lifecycle test --

#[test]
fn test_full_lifecycle_closed_open_halfopen_closed() {
    let cb = CircuitBreaker::new(make_config(50));

    // Phase 1: Closed — requests work
    assert_eq!(cb.state(), CircuitState::Closed);
    assert!(cb.check().is_ok());

    // Phase 2: Accumulate failures to trip
    cb.record_success();
    cb.record_success();
    cb.record_failure();
    cb.record_failure();
    assert_eq!(cb.state(), CircuitState::Open);

    // Phase 3: Wait for cooldown, transition to HalfOpen
    std::thread::sleep(Duration::from_millis(60));
    assert!(cb.check().is_ok());
    assert_eq!(cb.state(), CircuitState::HalfOpen);

    // Phase 4: Probe succeeds, back to Closed
    cb.record_success();
    assert_eq!(cb.state(), CircuitState::Closed);
    assert!(cb.check().is_ok());
}

#[test]
fn test_full_lifecycle_with_repeated_failures() {
    let cb = CircuitBreaker::new(make_config(50));

    // Trip the circuit
    cb.record_success();
    cb.record_success();
    cb.record_failure();
    cb.record_failure();
    assert_eq!(cb.state(), CircuitState::Open);

    // First recovery attempt fails
    std::thread::sleep(Duration::from_millis(60));
    assert!(cb.check().is_ok()); // -> HalfOpen
    cb.record_failure(); // -> Open again
    assert_eq!(cb.state(), CircuitState::Open);

    // Second recovery attempt succeeds
    std::thread::sleep(Duration::from_millis(60));
    assert!(cb.check().is_ok()); // -> HalfOpen
    cb.record_success(); // -> Closed
    assert_eq!(cb.state(), CircuitState::Closed);
}
