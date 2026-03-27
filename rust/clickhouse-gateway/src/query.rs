use std::time::Instant;

use axum::extract::State;
use axum::Json;
use serde::{Deserialize, Serialize};
use tracing::{info, warn};
use uuid::Uuid;

use crate::cache::{self, CachedResult};
use crate::error::GatewayError;
use crate::routing::Workload;
use crate::state::AppState;
use crate::validation;

#[derive(Deserialize, Debug, Clone)]
pub struct QueryRequest {
    pub sql: String,
    pub params: Option<serde_json::Value>,
    /// ONLINE, OFFLINE, LOGS, ENDPOINTS, or DEFAULT.
    /// Defaults to "DEFAULT" when the caller (e.g. the Python GatewayClient)
    /// does not yet send routing metadata.
    #[serde(default = "default_workload")]
    pub workload: String,
    /// Caller identity: APP, API, BATCH_EXPORT, etc.
    #[serde(default = "default_ch_user")]
    pub ch_user: String,
    #[serde(default)]
    pub team_id: u64,
    #[serde(default)]
    pub org_id: Option<u64>,
    /// Defaults to `true` — safest assumption when the caller doesn't specify.
    #[serde(default = "default_read_only")]
    pub read_only: bool,
    #[serde(default)]
    pub priority: Option<String>,
    #[serde(default)]
    pub cache_ttl_seconds: Option<u64>,
    #[serde(default)]
    pub settings: Option<serde_json::Value>,
    #[serde(default)]
    pub query_tags: Option<serde_json::Value>,
    #[serde(default)]
    pub query_id: Option<String>,
    #[serde(default)]
    pub columnar: Option<bool>,
}

fn default_workload() -> String {
    "DEFAULT".to_string()
}

fn default_ch_user() -> String {
    "unknown".to_string()
}

fn default_read_only() -> bool {
    true
}

#[derive(Serialize, Debug)]
pub struct QueryResponse {
    pub data: serde_json::Value,
    pub rows: u64,
    pub bytes_read: u64,
    pub elapsed_ms: u64,
}

/// POST /query — the primary gateway endpoint.
///
/// 1. Validates the request (readonly check, settings ceiling)
/// 2. Checks the circuit breaker for the target workload
/// 3. Acquires a per-team concurrency permit
/// 4. Checks the Redis cache (if cache_ttl_seconds is set and query is read-only)
/// 5. Routes to the correct ClickHouse cluster based on workload
/// 6. Enforces max_execution_time from config (not caller-overridable)
/// 7. Constructs log_comment JSON with gateway tracing fields
/// 8. Forwards the query to ClickHouse via HTTP
/// 9. Records circuit breaker success/failure
/// 10. Stores the result in cache if applicable
/// 11. Records metrics and returns the response
pub async fn handle_query(
    State(state): State<AppState>,
    Json(req): Json<QueryRequest>,
) -> Result<Json<QueryResponse>, GatewayError> {
    let start = Instant::now();
    let gateway_request_id = Uuid::new_v4().to_string();

    // Parse and validate workload
    let workload =
        Workload::from_str_value(&req.workload).map_err(GatewayError::InvalidWorkload)?;

    // Validate read-only constraint
    validation::validate_readonly(&req)?;

    // Check circuit breaker before doing any work
    let breaker = state.circuit_breakers.get(workload.as_str());
    breaker.check()?;

    // Acquire per-team concurrency permit (RAII — released on drop)
    let _permit = state.team_limits.try_acquire(req.team_id, &req.ch_user)?;

    // Get workload limits from config
    let (max_concurrent, max_execution_time) = state.config.limits_for_workload(&workload);

    // Check cache for read queries with a cache TTL
    let is_write = cache::is_write_query(&req.sql);
    let cache_key = if !is_write && req.cache_ttl_seconds.is_some() {
        let key = cache::compute_cache_key(req.team_id, &req.sql, &req.params);
        if let Some(cached) = state.cache.get(req.team_id, &key).await {
            metrics::counter!("gateway_cache_hits_total").increment(1);
            let elapsed_ms = start.elapsed().as_millis() as u64;
            return Ok(Json(QueryResponse {
                data: cached.data,
                rows: cached.rows,
                bytes_read: cached.bytes_read,
                elapsed_ms,
            }));
        }
        metrics::counter!("gateway_cache_misses_total").increment(1);
        Some(key)
    } else {
        None
    };

    // Filter settings through allowlist, then enforce ceiling
    let mut settings = validation::filter_settings(
        &req.settings
            .clone()
            .unwrap_or_else(|| serde_json::json!({})),
    );
    validation::enforce_settings_ceiling(&mut settings, max_execution_time);

    // Always set max_execution_time to the config ceiling
    if let Some(obj) = settings.as_object_mut() {
        obj.entry("max_execution_time".to_string())
            .or_insert_with(|| serde_json::Value::Number(max_execution_time.into()));
    }

    // Build log_comment with gateway tracing fields (request ID + version)
    let log_comment = crate::tagging::build_log_comment(&req.query_tags, &gateway_request_id);

    // Route to the correct cluster host
    let host = state.router.route(&workload);

    // Estimate query cost before execution
    let cost = state
        .scheduler
        .estimate_cost(&state.http_client, host, &req.sql, workload.as_str())
        .await;

    info!(
        team_id = req.team_id,
        workload = workload.as_str(),
        ch_user = %req.ch_user,
        host = %host,
        slot_weight = cost.slot_weight,
        method = ?cost.method,
        gateway_request_id = %gateway_request_id,
        // Per-team concurrency enforced via TeamLimits. Global per-workload
        // semaphore can be added here if needed (tokio::sync::Semaphore in AppState).
        max_concurrent = max_concurrent,
        "routing query"
    );

    metrics::histogram!("gateway_query_cost_estimate", "workload" => workload.as_str().to_string())
        .record(cost.slot_weight);

    // Forward to ClickHouse via HTTP POST
    let response = execute_clickhouse_query(
        &state.http_client,
        &ClickHouseQueryParams {
            host,
            sql: &req.sql,
            params: &req.params,
            settings: &settings,
            log_comment: &log_comment,
            max_execution_time,
            query_id: &req.query_id,
            gateway_request_id: &gateway_request_id,
        },
    )
    .await;

    // Record circuit breaker outcome
    match &response {
        Ok(_) => breaker.record_success(),
        Err(GatewayError::ClickHouseError(_) | GatewayError::Timeout(_)) => {
            breaker.record_failure();
        }
        Err(_) => {
            // Client errors (validation, etc.) don't count as backend failures
        }
    }

    let response = response?;

    // Store in cache if applicable
    if let Some(ref key) = cache_key {
        if let Some(ttl) = req.cache_ttl_seconds {
            let cached = CachedResult {
                data: response.data.clone(),
                rows: response.rows,
                bytes_read: response.bytes_read,
            };
            state.cache.set(req.team_id, key, &cached, ttl).await;
        }
    }

    let elapsed_ms = start.elapsed().as_millis() as u64;

    // Record metrics
    let labels = [
        ("workload".to_string(), workload.as_str().to_string()),
        ("ch_user".to_string(), req.ch_user.clone()),
    ];
    metrics::counter!("gateway_queries_total", &labels).increment(1);
    metrics::histogram!("gateway_query_duration_ms", &labels).record(elapsed_ms as f64);

    Ok(Json(QueryResponse {
        data: response.data,
        rows: response.rows,
        bytes_read: response.bytes_read,
        elapsed_ms,
    }))
}

struct ClickHouseResponse {
    data: serde_json::Value,
    rows: u64,
    bytes_read: u64,
}

struct ClickHouseQueryParams<'a> {
    host: &'a str,
    sql: &'a str,
    params: &'a Option<serde_json::Value>,
    settings: &'a serde_json::Value,
    log_comment: &'a str,
    max_execution_time: u32,
    query_id: &'a Option<String>,
    gateway_request_id: &'a str,
}

async fn execute_clickhouse_query(
    client: &reqwest::Client,
    params: &ClickHouseQueryParams<'_>,
) -> Result<ClickHouseResponse, GatewayError> {
    let url = format!("{}/", params.host);
    let sql = params.sql;
    let max_execution_time = params.max_execution_time;

    // Build query parameters for the ClickHouse HTTP interface
    let mut query_params: Vec<(String, String)> = vec![
        ("log_comment".to_string(), params.log_comment.to_string()),
        (
            "max_execution_time".to_string(),
            max_execution_time.to_string(),
        ),
        (
            "output_format_json_quote_64bit_integers".to_string(),
            "0".to_string(),
        ),
    ];

    // Forward caller-supplied query_id for distributed tracing and query cancellation
    if let Some(qid) = params.query_id {
        query_params.push(("query_id".to_string(), qid.clone()));
    }

    // Merge caller settings into query params
    if let Some(obj) = params.settings.as_object() {
        for (k, v) in obj {
            if k == "max_execution_time" {
                continue; // already set above at the ceiling
            }
            let val = match v {
                serde_json::Value::String(s) => s.clone(),
                other => other.to_string(),
            };
            query_params.push((k.clone(), val));
        }
    }

    // Add parameterized query params (param_X for ClickHouse)
    if let Some(p) = params.params {
        if let Some(obj) = p.as_object() {
            for (k, v) in obj {
                let val = match v {
                    serde_json::Value::String(s) => s.clone(),
                    other => other.to_string(),
                };
                query_params.push((format!("param_{k}"), val));
            }
        }
    }

    // Use the shared write-query detector (covers INSERT, ALTER, DROP, CREATE,
    // TRUNCATE, OPTIMIZE, SYSTEM, RENAME, ATTACH, DETACH, KILL)
    let is_write = cache::is_write_query(sql);

    let body = if is_write {
        sql.to_string()
    } else {
        format!("{sql} FORMAT JSON")
    };

    // Per-request timeout: max_execution_time + 5s buffer for network overhead.
    // The client-level timeout (605s) remains as a safety backstop.
    let request_timeout = std::time::Duration::from_secs(max_execution_time as u64 + 5);

    let resp = client
        .post(&url)
        .query(&query_params)
        .header("Content-Type", "text/plain")
        .timeout(request_timeout)
        .body(body)
        .send()
        .await
        .map_err(|e| {
            warn!(error = %e, "clickhouse request failed");
            if e.is_timeout() {
                GatewayError::Timeout(max_execution_time)
            } else {
                GatewayError::ClickHouseError(e.to_string())
            }
        })?;

    let status = resp.status();
    let body = resp
        .text()
        .await
        .map_err(|e| GatewayError::ClickHouseError(format!("failed to read response body: {e}")))?;

    if !status.is_success() {
        // Log the full ClickHouse error for debugging, but return a sanitized
        // message to the caller to avoid leaking schema, hostnames, or credentials.
        warn!(
            status = %status,
            gateway_request_id = %params.gateway_request_id,
            body_prefix = &body[..body.len().min(500)],
            "clickhouse returned error"
        );
        return Err(GatewayError::ClickHouseError(format!(
            "ClickHouse returned {status} (gateway_request_id={rid})",
            rid = params.gateway_request_id,
        )));
    }

    // Write queries (DDL, INSERT) return empty body — handle gracefully
    if is_write || body.trim().is_empty() {
        return Ok(ClickHouseResponse {
            data: serde_json::Value::Array(vec![]),
            rows: 0,
            bytes_read: 0,
        });
    }

    // Parse ClickHouse JSON response
    let parsed: serde_json::Value = serde_json::from_str(&body).map_err(|e| {
        GatewayError::ClickHouseError(format!("failed to parse response JSON: {e}"))
    })?;

    let rows = parsed["rows"].as_u64().unwrap_or(0);

    let bytes_read = parsed["statistics"]["bytes_read"].as_u64().unwrap_or(0);

    Ok(ClickHouseResponse {
        data: parsed
            .get("data")
            .cloned()
            .unwrap_or(serde_json::Value::Array(vec![])),
        rows,
        bytes_read,
    })
}

// --- /estimate-cost endpoint ---

#[derive(Deserialize, Debug)]
pub struct EstimateCostRequest {
    pub sql: String,
    #[serde(default = "default_workload")]
    pub workload: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct EstimateCostResponse {
    pub slot_weight: f64,
    pub estimated_rows: u64,
    pub uses_index: bool,
    pub method: crate::scheduling::CostMethod,
}

/// POST /estimate-cost — returns the estimated cost of a query without executing it.
///
/// Uses the same EXPLAIN-based or heuristic logic as the /query path, but skips
/// execution, caching, circuit breakers, and team limits. Useful for callers that
/// want to preview how expensive a query would be before committing to it.
pub async fn handle_estimate_cost(
    State(state): State<AppState>,
    Json(req): Json<EstimateCostRequest>,
) -> Result<Json<EstimateCostResponse>, GatewayError> {
    let workload =
        Workload::from_str_value(&req.workload).map_err(GatewayError::InvalidWorkload)?;

    let host = state.router.route(&workload);

    let cost = state
        .scheduler
        .estimate_cost(&state.http_client, host, &req.sql, workload.as_str())
        .await;

    Ok(Json(EstimateCostResponse {
        slot_weight: cost.slot_weight,
        estimated_rows: cost.estimated_rows,
        uses_index: cost.uses_index,
        method: cost.method,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use axum::routing::post;
    use axum::Router;
    use tower::ServiceExt;

    use crate::config::test_config;
    use crate::state::AppState;

    fn test_app() -> Router {
        let state = AppState::new(test_config());
        Router::new()
            .route("/estimate-cost", post(handle_estimate_cost))
            .with_state(state)
    }

    #[tokio::test]
    async fn test_estimate_cost_simple_select() {
        let app = test_app();
        let body = serde_json::json!({
            "sql": "SELECT 1",
            "workload": "OFFLINE"
        });

        let resp = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/estimate-cost")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let result: EstimateCostResponse = serde_json::from_slice(&body).unwrap();
        assert_eq!(result.slot_weight, 0.1); // SELECT 1 is trivial
        assert_eq!(result.method, crate::scheduling::CostMethod::Heuristic);
    }

    #[tokio::test]
    async fn test_estimate_cost_complex_query() {
        let app = test_app();
        let body = serde_json::json!({
            "sql": "SELECT count() FROM events JOIN persons ON events.person_id = persons.id GROUP BY person_id",
            "workload": "OFFLINE"
        });

        let resp = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/estimate-cost")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let result: EstimateCostResponse = serde_json::from_slice(&body).unwrap();
        // JOIN + no WHERE + GROUP BY = 1.0 + 1.5 + 3.0 + 0.5 = 6.0
        assert!((result.slot_weight - 6.0).abs() < 0.01);
        assert!(!result.uses_index);
    }

    #[tokio::test]
    async fn test_estimate_cost_defaults_workload() {
        let app = test_app();
        // Omit workload — should default to "DEFAULT"
        let body = serde_json::json!({ "sql": "DESCRIBE TABLE events" });

        let resp = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/estimate-cost")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let result: EstimateCostResponse = serde_json::from_slice(&body).unwrap();
        assert_eq!(result.slot_weight, 0.1); // DESCRIBE is cheap
    }

    #[tokio::test]
    async fn test_estimate_cost_invalid_workload() {
        let app = test_app();
        let body = serde_json::json!({
            "sql": "SELECT 1",
            "workload": "INVALID_WORKLOAD"
        });

        let resp = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/estimate-cost")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_estimate_cost_missing_sql() {
        let app = test_app();
        let body = serde_json::json!({ "workload": "ONLINE" });

        let resp = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/estimate-cost")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        // Missing required field → 422 (Axum JSON rejection)
        assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
    }

    #[test]
    fn test_estimate_cost_request_deserialization() {
        let json = r#"{"sql": "SELECT 1"}"#;
        let req: EstimateCostRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.sql, "SELECT 1");
        assert_eq!(req.workload, "DEFAULT"); // default
    }

    #[test]
    fn test_estimate_cost_response_serialization() {
        let resp = EstimateCostResponse {
            slot_weight: 1.5,
            estimated_rows: 8192,
            uses_index: true,
            method: crate::scheduling::CostMethod::Explain,
        };
        let json = serde_json::to_value(&resp).unwrap();
        assert_eq!(json["slot_weight"], 1.5);
        assert_eq!(json["estimated_rows"], 8192);
        assert_eq!(json["uses_index"], true);
        assert_eq!(json["method"], "explain");
    }
}
