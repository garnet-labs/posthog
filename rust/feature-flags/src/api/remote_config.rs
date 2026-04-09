use crate::{
    config_cache::get_cached_config, handler::config_response_builder::sanitize_config_for_client,
    router::State as AppState,
};
use axum::{
    debug_handler,
    extract::{Path, State},
    http::{HeaderMap, Method, StatusCode},
    response::{IntoResponse, Json, Response},
};
use common_metrics::inc;
use serde_json::Value;
use tracing::info;

const REMOTE_CONFIG_COUNTER: &str = "remote_config_requests_total";

/// Validate a project API token.
///
/// Matches Django's `BaseRemoteConfigAPIView.check_token`:
/// - Max 200 characters
/// - Only alphanumeric, underscore, and hyphen
fn is_valid_token(token: &str) -> bool {
    token.len() <= 200
        && !token.is_empty()
        && token
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}

/// Cache-Control and Vary headers matching Django's `add_config_cache_headers`.
fn config_cache_headers() -> [(&'static str, &'static str); 2] {
    [
        ("cache-control", "public, max-age=300"),
        ("vary", "Origin, Referer"),
    ]
}

/// Fetch config from HyperCache, returning the raw value.
///
/// Returns `Ok(config)` on hit, or an HTTP error response on failure:
/// - 400 for invalid tokens
/// - 404 for unknown tokens (cache miss / explicit missing marker)
async fn get_validated_config(
    state: &AppState,
    token: &str,
    endpoint_label: &str,
) -> Result<Value, Response> {
    if !is_valid_token(token) {
        inc(
            REMOTE_CONFIG_COUNTER,
            &[
                ("endpoint".to_string(), endpoint_label.to_string()),
                ("result".to_string(), "invalid_token".to_string()),
            ],
            1,
        );
        return Err((StatusCode::BAD_REQUEST, "Invalid token").into_response());
    }

    match get_cached_config(&state.config_hypercache_reader, token).await {
        Some(value) => {
            inc(
                REMOTE_CONFIG_COUNTER,
                &[
                    ("endpoint".to_string(), endpoint_label.to_string()),
                    ("result".to_string(), "hit".to_string()),
                ],
                1,
            );
            Ok(value)
        }
        None => {
            inc(
                REMOTE_CONFIG_COUNTER,
                &[
                    ("endpoint".to_string(), endpoint_label.to_string()),
                    ("result".to_string(), "not_found".to_string()),
                ],
                1,
            );
            info!(token = %token, "Remote config not found");
            Err(StatusCode::NOT_FOUND.into_response())
        }
    }
}

/// `GET /array/:token/config` — returns JSON config blob.
///
/// Reads pre-computed config from HyperCache (written by Django's RemoteConfig.sync).
/// Public endpoint — no auth beyond token validation.
///
/// Response headers: `Cache-Control: public, max-age=300`, `Vary: Origin, Referer`
#[debug_handler]
pub async fn config_endpoint(
    State(state): State<AppState>,
    Path(token): Path<String>,
    headers: HeaderMap,
    method: Method,
) -> Response {
    if method == Method::OPTIONS {
        return (StatusCode::NO_CONTENT, [("allow", "GET, OPTIONS, HEAD")]).into_response();
    }

    // Validate token before HEAD so invalid/missing tokens return 400/404, not 200
    let mut config = match get_validated_config(&state, &token, "config").await {
        Ok(c) => c,
        Err(r) => return r,
    };

    if method == Method::HEAD {
        return (
            StatusCode::OK,
            config_cache_headers(),
            [("content-type", "application/json")],
            axum::body::Body::empty(),
        )
            .into_response();
    }

    sanitize_config_for_client(&mut config, &headers);

    (StatusCode::OK, config_cache_headers(), Json(config)).into_response()
}

/// `GET /array/:token/config.js` — returns JS wrapper around config.
///
/// Wraps the config JSON in an IIFE that sets `window._POSTHOG_REMOTE_CONFIG[token]`
/// with the config and site apps. This is what the SDK snippet loads.
///
/// Response headers: same cache headers + `Content-Type: application/javascript`
#[debug_handler]
pub async fn config_js_endpoint(
    State(state): State<AppState>,
    Path(token): Path<String>,
    headers: HeaderMap,
    method: Method,
) -> Response {
    if method == Method::OPTIONS {
        return (StatusCode::NO_CONTENT, [("allow", "GET, OPTIONS, HEAD")]).into_response();
    }

    // Validate token before HEAD so invalid/missing tokens return 400/404, not 200
    let mut config = match get_validated_config(&state, &token, "config_js").await {
        Ok(c) => c,
        Err(r) => return r,
    };

    if method == Method::HEAD {
        return (
            StatusCode::OK,
            [
                ("content-type", "application/javascript"),
                ("cache-control", "public, max-age=300"),
                ("vary", "Origin, Referer"),
            ],
            axum::body::Body::empty(),
        )
            .into_response();
    }

    // Extract siteAppsJS (raw JS strings) before sanitization removes it
    let site_apps_js = config
        .as_object_mut()
        .and_then(|obj| obj.remove("siteAppsJS"))
        .and_then(|v| {
            if let Value::Array(arr) = v {
                Some(
                    arr.into_iter()
                        .filter_map(|item| {
                            if let Value::String(s) = item {
                                Some(s)
                            } else {
                                None
                            }
                        })
                        .collect::<Vec<String>>(),
                )
            } else {
                None
            }
        })
        .unwrap_or_default();

    // Remove siteApps (minimal metadata) — the JS version has the full JS instead
    if let Some(obj) = config.as_object_mut() {
        obj.remove("siteApps");
    }

    sanitize_config_for_client(&mut config, &headers);

    let config_json = serde_json::to_string(&config).unwrap_or_else(|_| "{}".to_string());
    let site_apps_joined = site_apps_js.join(",");

    let js_content = build_config_js(&token, &config_json, &site_apps_joined);

    (
        StatusCode::OK,
        [
            ("content-type", "application/javascript"),
            ("cache-control", "public, max-age=300"),
            ("vary", "Origin, Referer"),
        ],
        js_content,
    )
        .into_response()
}

/// Build the JS IIFE that sets `window._POSTHOG_REMOTE_CONFIG[token]`.
fn build_config_js(token: &str, config_json: &str, site_apps_joined: &str) -> String {
    format!(
        "(function() {{\n\
         \x20 window._POSTHOG_REMOTE_CONFIG = window._POSTHOG_REMOTE_CONFIG || {{}};\n\
         \x20 window._POSTHOG_REMOTE_CONFIG['{token}'] = {{\n\
         \x20   config: {config_json},\n\
         \x20   siteApps: [{site_apps_joined}]\n\
         \x20 }}\n\
         }})();"
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_valid_tokens() {
        assert!(is_valid_token("phc_abc123"));
        assert!(is_valid_token(
            "phc_leDMtGUQ1TDiPxotanVngOdEsShwcpDsLFLROFcGK9W"
        ));
        assert!(is_valid_token("some-old-token_with-dashes"));
        assert!(is_valid_token("a"));
    }

    #[test]
    fn test_invalid_tokens() {
        assert!(!is_valid_token(""));
        assert!(!is_valid_token("token with spaces"));
        assert!(!is_valid_token("token/with/slashes"));
        assert!(!is_valid_token("token.with.dots"));
        assert!(!is_valid_token(&"a".repeat(201)));
    }

    #[test]
    fn test_config_js_template_format() {
        let config = json!({"sessionRecording": true, "heatmaps": false});
        let config_json = serde_json::to_string(&config).unwrap();

        let js = build_config_js("phc_test123", &config_json, "");

        assert!(js.contains("window._POSTHOG_REMOTE_CONFIG"));
        assert!(js.contains("phc_test123"));
        assert!(js.contains("\"sessionRecording\":true"));
        assert!(js.contains("siteApps: []"));
    }

    #[test]
    fn test_config_js_template_with_site_apps() {
        let site_apps_joined = "function() { return 1; },function() { return 2; }";

        let js = build_config_js("phc_test", "{}", site_apps_joined);

        assert!(js.contains("siteApps: [function() { return 1; },function() { return 2; }]"));
    }
}
