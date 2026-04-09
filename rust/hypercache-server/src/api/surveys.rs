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
/// - Token passed as query param (Django also accepts form body, not yet supported here)
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
    use crate::test_utils::helpers::*;
    use axum::http::StatusCode;
    use common_redis::MockRedisClient;
    use serde_json::json;

    #[test]
    fn test_query_params_deserialize() {
        let params: SurveysQueryParams = serde_json::from_str(r#"{"token": "phc_test"}"#).unwrap();
        assert_eq!(params.token.as_deref(), Some("phc_test"));
    }

    #[tokio::test]
    async fn test_missing_token_returns_401() {
        let surveys = mock_reader("surveys", "surveys.json", MockRedisClient::new()).await;
        let config = mock_reader("array", "config.json", MockRedisClient::new()).await;
        let router = test_router(surveys, config);

        let (status, _body) = get(&router, "/api/surveys").await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_cache_miss_returns_empty_surveys() {
        let surveys = mock_reader("surveys", "surveys.json", MockRedisClient::new()).await;
        let config = mock_reader("array", "config.json", MockRedisClient::new()).await;
        let router = test_router(surveys, config);

        let (status, body) = get(&router, "/api/surveys?token=phc_unknown").await;
        assert_eq!(status, StatusCode::OK);

        let parsed: serde_json::Value = serde_json::from_str(&body).unwrap();
        assert_eq!(parsed["surveys"], json!([]));
        assert_eq!(parsed["survey_config"], json!(null));
    }

    #[tokio::test]
    async fn test_cache_hit_returns_survey_data() {
        let token = "phc_test_surveys";
        let key = cache_key("surveys", "surveys.json", token);

        let survey_data = json!({
            "surveys": [{"id": "s1", "name": "NPS", "type": "popover"}],
            "survey_config": {"appearance": {"theme": "light"}}
        });

        let mut mock = MockRedisClient::new();
        mock = mock.get_raw_bytes_ret(&key, Ok(pickle_json(&survey_data)));

        let surveys = mock_reader("surveys", "surveys.json", mock).await;
        let config = mock_reader("array", "config.json", MockRedisClient::new()).await;
        let router = test_router(surveys, config);

        let (status, body) = get(&router, &format!("/api/surveys?token={token}")).await;
        assert_eq!(status, StatusCode::OK);

        let parsed: serde_json::Value = serde_json::from_str(&body).unwrap();
        assert_eq!(parsed, survey_data);
    }
}
