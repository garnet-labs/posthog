use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Serialize;

#[derive(Debug, thiserror::Error)]
pub enum GatewayError {
    #[error("invalid workload: {0}")]
    InvalidWorkload(String),

    #[error("write queries are not allowed when read_only is true")]
    WriteNotAllowed,

    #[error("invalid request: {0}")]
    InvalidRequest(String),

    #[error("clickhouse error: {0}")]
    ClickHouseError(String),

    #[error("upstream timeout after {0}s")]
    Timeout(u32),

    #[error("circuit breaker open for workload: {0}")]
    CircuitBreakerOpen(String),

    #[error("team {team_id} exceeded {ch_user} concurrency limit of {limit}")]
    TeamConcurrencyLimit {
        team_id: u64,
        ch_user: String,
        limit: u32,
    },

    #[error("internal error: {0}")]
    Internal(String),
}

#[derive(Serialize)]
struct ErrorResponse {
    error: String,
    error_type: String,
}

impl GatewayError {
    pub fn error_type(&self) -> &'static str {
        match self {
            GatewayError::InvalidWorkload(_) => "invalid_workload",
            GatewayError::WriteNotAllowed => "write_not_allowed",
            GatewayError::InvalidRequest(_) => "invalid_request",
            GatewayError::ClickHouseError(_) => "clickhouse_error",
            GatewayError::Timeout(_) => "timeout",
            GatewayError::CircuitBreakerOpen(_) => "circuit_breaker_open",
            GatewayError::TeamConcurrencyLimit { .. } => "team_concurrency_limit",
            GatewayError::Internal(_) => "internal_error",
        }
    }

    pub fn status_code(&self) -> StatusCode {
        match self {
            GatewayError::InvalidWorkload(_) => StatusCode::BAD_REQUEST,
            GatewayError::WriteNotAllowed => StatusCode::FORBIDDEN,
            GatewayError::InvalidRequest(_) => StatusCode::BAD_REQUEST,
            GatewayError::ClickHouseError(_) => StatusCode::BAD_GATEWAY,
            GatewayError::Timeout(_) => StatusCode::GATEWAY_TIMEOUT,
            GatewayError::CircuitBreakerOpen(_) => StatusCode::SERVICE_UNAVAILABLE,
            GatewayError::TeamConcurrencyLimit { .. } => StatusCode::TOO_MANY_REQUESTS,
            GatewayError::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }
}

impl IntoResponse for GatewayError {
    fn into_response(self) -> Response {
        let status = self.status_code();
        let body = ErrorResponse {
            error: self.to_string(),
            error_type: self.error_type().to_string(),
        };
        (status, Json(body)).into_response()
    }
}
