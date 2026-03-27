use std::collections::HashMap;

use clickhouse_gateway::error::GatewayError;
use clickhouse_gateway::tagging;
use clickhouse_gateway::team_limits::TeamLimits;

// ---------------------------------------------------------------------------
// TeamLimits tests
// ---------------------------------------------------------------------------

fn limits_with(user: &str, max: u32) -> TeamLimits {
    let mut limits = HashMap::new();
    limits.insert(user.to_string(), max);
    TeamLimits::with_limits(limits)
}

fn multi_limits(entries: &[(&str, u32)]) -> TeamLimits {
    let limits: HashMap<String, u32> = entries.iter().map(|(k, v)| (k.to_string(), *v)).collect();
    TeamLimits::with_limits(limits)
}

#[test]
fn test_acquire_within_limit() {
    let tl = limits_with("API", 3);

    let _p1 = tl.try_acquire(1, "API").unwrap();
    let _p2 = tl.try_acquire(1, "API").unwrap();
    let _p3 = tl.try_acquire(1, "API").unwrap();

    assert_eq!(tl.current_count(1, "API"), 3);
}

#[test]
fn test_acquire_exceeds_limit_rejected() {
    let tl = limits_with("API", 2);

    let _p1 = tl.try_acquire(1, "API").unwrap();
    let _p2 = tl.try_acquire(1, "API").unwrap();

    let result = tl.try_acquire(1, "API");
    assert!(result.is_err());

    match result.unwrap_err() {
        GatewayError::TeamConcurrencyLimit {
            team_id,
            ch_user,
            limit,
        } => {
            assert_eq!(team_id, 1);
            assert_eq!(ch_user, "API");
            assert_eq!(limit, 2);
        }
        other => panic!("expected TeamConcurrencyLimit, got: {other:?}"),
    }
}

#[test]
fn test_permit_drop_releases_slot() {
    let tl = limits_with("APP", 1);

    // Acquire and then drop.
    {
        let _p = tl.try_acquire(10, "APP").unwrap();
        assert_eq!(tl.current_count(10, "APP"), 1);
        // _p drops here
    }

    assert_eq!(tl.current_count(10, "APP"), 0);

    // Can acquire again after release.
    let _p2 = tl
        .try_acquire(10, "APP")
        .expect("should succeed after release");
    assert_eq!(tl.current_count(10, "APP"), 1);
}

#[test]
fn test_different_teams_independent() {
    let tl = limits_with("API", 1);

    let _p1 = tl.try_acquire(1, "API").unwrap();
    // Team 1 is at limit — team 2 should still succeed.
    let _p2 = tl.try_acquire(2, "API").unwrap();

    assert_eq!(tl.current_count(1, "API"), 1);
    assert_eq!(tl.current_count(2, "API"), 1);

    // Team 1 is still at limit.
    assert!(tl.try_acquire(1, "API").is_err());
    // Team 2 is also at limit.
    assert!(tl.try_acquire(2, "API").is_err());
    // Team 3 is fine.
    let _p3 = tl.try_acquire(3, "API").unwrap();
}

#[test]
fn test_different_users_different_limits() {
    let tl = multi_limits(&[("API", 1), ("APP", 3), ("BATCH_EXPORT", 2)]);

    // API: limit 1
    let _p_api = tl.try_acquire(1, "API").unwrap();
    assert!(tl.try_acquire(1, "API").is_err());

    // APP: limit 3 — same team, different user
    let _p_app1 = tl.try_acquire(1, "APP").unwrap();
    let _p_app2 = tl.try_acquire(1, "APP").unwrap();
    let _p_app3 = tl.try_acquire(1, "APP").unwrap();
    assert!(tl.try_acquire(1, "APP").is_err());

    // BATCH_EXPORT: limit 2
    let _p_be1 = tl.try_acquire(1, "BATCH_EXPORT").unwrap();
    let _p_be2 = tl.try_acquire(1, "BATCH_EXPORT").unwrap();
    assert!(tl.try_acquire(1, "BATCH_EXPORT").is_err());
}

#[test]
fn test_case_insensitive_ch_user() {
    let tl = limits_with("API", 1);

    let _p = tl.try_acquire(1, "api").unwrap();
    // "Api" for the same team should be rejected — same bucket.
    assert!(tl.try_acquire(1, "Api").is_err());
}

#[test]
fn test_unknown_user_gets_fallback_limit() {
    // No explicit limits — all users get the fallback (5).
    let tl = TeamLimits::with_limits(HashMap::new());

    let mut permits = Vec::new();
    for _ in 0..5 {
        permits.push(tl.try_acquire(1, "UNKNOWN_USER").unwrap());
    }
    assert!(tl.try_acquire(1, "UNKNOWN_USER").is_err());
}

// ---------------------------------------------------------------------------
// Tagging (build_log_comment) tests
// ---------------------------------------------------------------------------

#[test]
fn test_build_log_comment_from_tags() {
    let tags = Some(serde_json::json!({
        "team_id": 42,
        "query_id": "q-001",
        "source": "trends"
    }));
    let result = tagging::build_log_comment(&tags, "gw-req-123");
    let parsed: serde_json::Value = serde_json::from_str(&result).unwrap();

    assert_eq!(parsed["team_id"], 42);
    assert_eq!(parsed["query_id"], "q-001");
    assert_eq!(parsed["source"], "trends");
    assert_eq!(parsed["gateway_request_id"], "gw-req-123");
}

#[test]
fn test_log_comment_adds_gateway_fields() {
    let result = tagging::build_log_comment(&None, "gw-req-456");
    let parsed: serde_json::Value = serde_json::from_str(&result).unwrap();

    assert_eq!(parsed["gateway_request_id"], "gw-req-456");
    // gateway_version should be the crate version from Cargo.toml.
    assert!(
        parsed["gateway_version"].is_string(),
        "gateway_version should be a string"
    );
    assert!(
        !parsed["gateway_version"].as_str().unwrap().is_empty(),
        "gateway_version should not be empty"
    );
}

#[test]
fn test_log_comment_gateway_fields_override_caller_tags() {
    let tags = Some(serde_json::json!({
        "gateway_request_id": "should-be-overwritten",
        "gateway_version": "0.0.0",
        "custom_field": "preserved"
    }));
    let result = tagging::build_log_comment(&tags, "actual-id");
    let parsed: serde_json::Value = serde_json::from_str(&result).unwrap();

    assert_eq!(parsed["gateway_request_id"], "actual-id");
    assert_ne!(parsed["gateway_version"].as_str().unwrap(), "0.0.0");
    assert_eq!(parsed["custom_field"], "preserved");
}
