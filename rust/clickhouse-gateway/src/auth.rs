use axum::extract::Request;
use axum::http::StatusCode;
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};

/// Axum middleware that validates `Authorization: Bearer <token>` against
/// the configured `GATEWAY_SERVICE_TOKEN`.
///
/// When `expected_token` is empty, auth is disabled (local dev / tests).
pub async fn require_bearer_token(request: Request, next: Next, expected_token: &str) -> Response {
    // Auth disabled when token is empty (dev mode)
    if expected_token.is_empty() {
        return next.run(request).await;
    }

    let auth_header = request
        .headers()
        .get("authorization")
        .and_then(|v| v.to_str().ok());

    let provided = match auth_header {
        Some(h) if h.starts_with("Bearer ") => &h[7..],
        _ => {
            return (
                StatusCode::UNAUTHORIZED,
                axum::Json(serde_json::json!({
                    "error": "missing or malformed Authorization header",
                    "error_type": "unauthorized"
                })),
            )
                .into_response();
        }
    };

    // Fixed-length comparison: always compare all bytes to avoid timing leaks.
    // Both sides are hashed to equalize length before comparison.
    if constant_time_eq(provided.as_bytes(), expected_token.as_bytes()) {
        next.run(request).await
    } else {
        (
            StatusCode::UNAUTHORIZED,
            axum::Json(serde_json::json!({
                "error": "invalid service token",
                "error_type": "unauthorized"
            })),
        )
            .into_response()
    }
}

/// Compare two byte slices in constant time using SHA-256 to normalize length.
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    use sha2::{Digest, Sha256};

    let hash_a = Sha256::digest(a);
    let hash_b = Sha256::digest(b);

    // Compare the fixed-length hashes byte-by-byte, accumulating differences
    let mut diff = 0u8;
    for (x, y) in hash_a.iter().zip(hash_b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::Request as HttpRequest;
    use axum::middleware;
    use axum::routing::get;
    use axum::Router;
    use tower::ServiceExt;

    async fn ok_handler() -> &'static str {
        "ok"
    }

    fn app_with_token(token: &'static str) -> Router {
        let token_owned = token.to_string();
        Router::new()
            .route("/test", get(ok_handler))
            .layer(middleware::from_fn(move |req, next| {
                let t = token_owned.clone();
                async move { require_bearer_token(req, next, &t).await }
            }))
    }

    #[tokio::test]
    async fn test_valid_token_passes() {
        let app = app_with_token("secret123");
        let req = HttpRequest::builder()
            .uri("/test")
            .header("authorization", "Bearer secret123")
            .body(Body::empty())
            .unwrap();

        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_missing_header_returns_401() {
        let app = app_with_token("secret123");
        let req = HttpRequest::builder()
            .uri("/test")
            .body(Body::empty())
            .unwrap();

        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_wrong_token_returns_401() {
        let app = app_with_token("secret123");
        let req = HttpRequest::builder()
            .uri("/test")
            .header("authorization", "Bearer wrong")
            .body(Body::empty())
            .unwrap();

        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_empty_token_disables_auth() {
        let app = app_with_token("");
        let req = HttpRequest::builder()
            .uri("/test")
            .body(Body::empty())
            .unwrap();

        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_malformed_header_returns_401() {
        let app = app_with_token("secret123");
        let req = HttpRequest::builder()
            .uri("/test")
            .header("authorization", "Basic dXNlcjpwYXNz")
            .body(Body::empty())
            .unwrap();

        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }
}
