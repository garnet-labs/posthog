use clickhouse_gateway::config::Config;
use clickhouse_gateway::scheduling::{CostMethod, Scheduler};

fn make_config(explain_enabled: bool) -> Config {
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
        explain_enabled,
        metrics_port: 9090,
        log_level: "info".to_string(),
    }
}

fn make_scheduler() -> Scheduler {
    Scheduler::new(&make_config(true))
}

// -- Heuristic cost tests --

#[test]
fn test_heuristic_metadata_query_cheap() {
    let scheduler = make_scheduler();

    let describe = scheduler.heuristic_cost("DESCRIBE TABLE events");
    assert!((describe.slot_weight - 0.1).abs() < f64::EPSILON);
    assert!(describe.uses_index);
    assert_eq!(describe.method, CostMethod::Heuristic);

    let show = scheduler.heuristic_cost("SHOW TABLES");
    assert!((show.slot_weight - 0.1).abs() < f64::EPSILON);

    let system_columns =
        scheduler.heuristic_cost("SELECT * FROM system.columns WHERE table = 'events'");
    assert!((system_columns.slot_weight - 0.1).abs() < f64::EPSILON);
}

#[test]
fn test_heuristic_simple_select() {
    let scheduler = make_scheduler();
    let cost = scheduler.heuristic_cost(
        "SELECT count() FROM events WHERE team_id = 42 AND timestamp > now() - INTERVAL 1 DAY",
    );

    assert!((cost.slot_weight - 1.0).abs() < f64::EPSILON);
    assert!(!cost.uses_index);
    assert_eq!(cost.method, CostMethod::Heuristic);
}

#[test]
fn test_heuristic_no_where_clause() {
    let scheduler = make_scheduler();
    let cost = scheduler.heuristic_cost("SELECT count() FROM events");

    // base 1.0 + no WHERE 3.0 = 4.0
    assert!((cost.slot_weight - 4.0).abs() < f64::EPSILON);
    assert!(!cost.uses_index);
}

#[test]
fn test_heuristic_join_increases_cost() {
    let scheduler = make_scheduler();

    let one_join = scheduler.heuristic_cost(
        "SELECT e.event FROM events e JOIN persons p ON e.person_id = p.id WHERE e.team_id = 1",
    );
    // base 1.0 + 1 JOIN * 1.5 = 2.5
    assert!((one_join.slot_weight - 2.5).abs() < f64::EPSILON);

    let two_joins = scheduler.heuristic_cost(
        "SELECT e.event FROM events e JOIN persons p ON e.person_id = p.id JOIN groups g ON e.group_id = g.id WHERE e.team_id = 1",
    );
    // base 1.0 + 2 JOINs * 1.5 = 4.0
    assert!((two_joins.slot_weight - 4.0).abs() < f64::EPSILON);
}

#[test]
fn test_heuristic_group_by_adds_cost() {
    let scheduler = make_scheduler();
    let cost = scheduler
        .heuristic_cost("SELECT event, count() FROM events WHERE team_id = 1 GROUP BY event");

    // base 1.0 + GROUP BY 0.5 = 1.5
    assert!((cost.slot_weight - 1.5).abs() < f64::EPSILON);
}

#[test]
fn test_heuristic_distinct_adds_cost() {
    let scheduler = make_scheduler();
    let cost = scheduler.heuristic_cost("SELECT DISTINCT event FROM events WHERE team_id = 1");

    // base 1.0 + DISTINCT 0.5 = 1.5
    assert!((cost.slot_weight - 1.5).abs() < f64::EPSILON);
}

#[test]
fn test_heuristic_max_cap_at_10() {
    let scheduler = make_scheduler();
    // 6 JOINs (9.0) + base (1.0) + no WHERE (3.0) + GROUP BY (0.5) + DISTINCT (0.5) = 14.0 -> capped at 10.0
    let cost = scheduler.heuristic_cost(
        "SELECT DISTINCT x FROM a JOIN b ON 1=1 JOIN c ON 1=1 JOIN d ON 1=1 JOIN e ON 1=1 JOIN f ON 1=1 JOIN g ON 1=1 GROUP BY x",
    );
    assert!((cost.slot_weight - 10.0).abs() < f64::EPSILON);
}

#[test]
fn test_heuristic_select_1_is_cheap() {
    let scheduler = make_scheduler();
    let cost = scheduler.heuristic_cost("SELECT 1");

    assert!((cost.slot_weight - 0.1).abs() < f64::EPSILON);
    assert!(cost.uses_index);
    assert_eq!(cost.method, CostMethod::Heuristic);
}

#[test]
fn test_cost_method_enum() {
    // Verify the three variants are distinct
    assert_ne!(CostMethod::Explain, CostMethod::Heuristic);
    assert_ne!(CostMethod::Heuristic, CostMethod::Default);
    assert_ne!(CostMethod::Explain, CostMethod::Default);

    // Verify debug output
    assert_eq!(format!("{:?}", CostMethod::Explain), "Explain");
    assert_eq!(format!("{:?}", CostMethod::Heuristic), "Heuristic");
    assert_eq!(format!("{:?}", CostMethod::Default), "Default");
}

// -- estimate_cost dispatch tests --

#[tokio::test]
async fn test_estimate_cost_offline_uses_heuristic() {
    let scheduler = make_scheduler();
    let client = reqwest::Client::new();

    let cost = scheduler
        .estimate_cost(&client, "http://localhost:9999", "SELECT 1", "OFFLINE")
        .await;

    // OFFLINE never uses EXPLAIN, always heuristic
    assert_eq!(cost.method, CostMethod::Heuristic);
}

#[tokio::test]
async fn test_estimate_cost_online_explain_disabled_uses_heuristic() {
    let config = make_config(false);
    let scheduler = Scheduler::new(&config);
    let client = reqwest::Client::new();

    let cost = scheduler
        .estimate_cost(&client, "http://localhost:9999", "SELECT 1", "ONLINE")
        .await;

    // EXPLAIN disabled -> heuristic
    assert_eq!(cost.method, CostMethod::Heuristic);
}

#[tokio::test]
async fn test_estimate_cost_online_explain_fallback_on_error() {
    let scheduler = make_scheduler();
    let client = reqwest::Client::new();

    // Connecting to a non-existent host will fail, triggering heuristic fallback
    let cost = scheduler
        .estimate_cost(
            &client,
            "http://127.0.0.1:19999",
            "SELECT count() FROM events WHERE team_id = 1",
            "ONLINE",
        )
        .await;

    // Should fall back to heuristic on connection error
    assert_eq!(cost.method, CostMethod::Heuristic);
    assert!((cost.slot_weight - 1.0).abs() < f64::EPSILON);
}

#[test]
fn test_heuristic_combined_complexity() {
    let scheduler = make_scheduler();

    // JOIN + GROUP BY + DISTINCT, with WHERE
    let cost = scheduler.heuristic_cost(
        "SELECT DISTINCT event, count() FROM events e JOIN persons p ON e.person_id = p.id WHERE e.team_id = 1 GROUP BY event",
    );

    // base 1.0 + JOIN 1.5 + GROUP BY 0.5 + DISTINCT 0.5 = 3.5
    assert!((cost.slot_weight - 3.5).abs() < f64::EPSILON);
}

#[test]
fn test_heuristic_case_insensitive() {
    let scheduler = make_scheduler();

    let cost = scheduler.heuristic_cost("describe table events");
    assert!((cost.slot_weight - 0.1).abs() < f64::EPSILON);

    let cost = scheduler.heuristic_cost("show tables");
    assert!((cost.slot_weight - 0.1).abs() < f64::EPSILON);
}
