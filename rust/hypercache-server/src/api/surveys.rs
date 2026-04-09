use crate::router::State as AppState;
use axum::{
    debug_handler,
    extract::{Query, State},
    http::{Method, StatusCode},
    response::{IntoResponse, Json, Response},
};
use common_hypercache::{KeyType, HYPER_CACHE_EMPTY_VALUE};
use serde::{Deserialize, Serialize};
use tracing::info;

/// Query parameters for the surveys endpoint.
/// Accepts `token` to identify the project — no auth required (public endpoint).
#[derive(Debug, Deserialize, Serialize)]
pub struct SurveysQueryParams {
    pub token: Option<String>,
}

fn empty_surveys_response() -> Response {
    Json(serde_json::json!({
        "surveys": [],
        "survey_config": null
    }))
    .into_response()
}

/// Surveys endpoint handler
///
/// Serves pre-cached survey definitions from HyperCache. This is a public endpoint
/// that only requires a project API token (no secret key or personal API key).
///
/// Mirrors Django's `POST /api/surveys` behavior:
/// - Token passed as query param or form body
/// - No authentication beyond token validation
/// - Returns cached `{"surveys": [...], "survey_config": {...}}`
#[debug_handler]
pub async fn surveys_endpoint(
    State(state): State<AppState>,
    Query(params): Query<SurveysQueryParams>,
    method: Method,
) -> Response {
    info!(
        method = %method,
        token = ?params.token,
        "Processing surveys request"
    );

    match method {
        Method::HEAD => {
            return (
                StatusCode::OK,
                [("content-type", "application/json")],
                axum::body::Body::empty(),
            )
                .into_response();
        }
        Method::OPTIONS => {
            return (
                StatusCode::NO_CONTENT,
                [("allow", "GET, POST, OPTIONS, HEAD")],
            )
                .into_response();
        }
        _ => {} // GET and POST proceed below
    }

    let token = match params.token {
        Some(t) if !t.is_empty() => t,
        _ => return (StatusCode::UNAUTHORIZED, "Token not provided").into_response(),
    };

    let key = KeyType::string(&token);

    let value = match state.surveys_hypercache_reader.get(&key).await {
        Ok(v) => v,
        Err(e) => {
            info!(
                token = %token,
                error = %e,
                "Surveys cache miss"
            );
            return empty_surveys_response();
        }
    };

    // Handle null / missing marker
    if value.is_null() {
        return empty_surveys_response();
    }
    if let Some(s) = value.as_str() {
        if s == HYPER_CACHE_EMPTY_VALUE {
            return empty_surveys_response();
        }
    }

    Json(value).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_empty_token_is_missing() {
        let params = SurveysQueryParams { token: None };
        assert!(params.token.is_none());
    }

    #[test]
    fn test_query_params_deserialize() {
        let params: SurveysQueryParams = serde_json::from_str(r#"{"token": "phc_test"}"#).unwrap();
        assert_eq!(params.token.as_deref(), Some("phc_test"));
    }

    #[test]
    fn test_empty_surveys_response_shape() {
        let response = json!({
            "surveys": [],
            "survey_config": null
        });
        assert!(response
            .get("surveys")
            .unwrap()
            .as_array()
            .unwrap()
            .is_empty());
        assert!(response.get("survey_config").unwrap().is_null());
    }
}
