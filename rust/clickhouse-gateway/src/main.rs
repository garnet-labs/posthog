use std::time::Duration;

use axum::extract::DefaultBodyLimit;
use axum::routing::{get, post};
use axum::Router;
use envconfig::Envconfig;
use tracing::level_filters::LevelFilter;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::{EnvFilter, Layer};

use clickhouse_gateway::auth::require_bearer_token;
use clickhouse_gateway::config::Config;
use clickhouse_gateway::query::{handle_estimate_cost, handle_query};
use clickhouse_gateway::state::AppState;

common_alloc::used!();

#[tokio::main]
async fn main() {
    let config = Config::init_from_env().expect("Invalid configuration:");

    // Initialize tracing
    let log_layer = tracing_subscriber::fmt::layer()
        .with_target(true)
        .with_thread_ids(true)
        .with_level(true)
        .json()
        .flatten_event(true)
        .with_span_list(true)
        .with_current_span(true)
        .with_filter(
            EnvFilter::builder()
                .with_default_directive(LevelFilter::INFO.into())
                .from_env_lossy(),
        )
        .boxed();

    tracing_subscriber::registry().with(log_layer).init();

    // Validate auth configuration — panics with a clear message if
    // GATEWAY_SERVICE_TOKEN is empty and auth is not explicitly disabled.
    config.validate_auth();

    // Root span with pod hostname for Loki/Grafana filtering
    let pod = std::env::var("HOSTNAME").unwrap_or_else(|_| "unknown".to_string());
    let _root_span = tracing::info_span!("service", pod = %pod).entered();

    let bind_addr = format!("{}:{}", config.host, config.port);
    let metrics_addr = format!("{}:{}", config.host, config.metrics_port);

    tracing::info!(
        bind = %bind_addr,
        metrics = %metrics_addr,
        "starting clickhouse-gateway"
    );

    let state = AppState::new(config.clone());

    // Spawn background task to evict idle team counters every 60s,
    // preventing the HashMap from growing without bound.
    state
        .team_limits
        .spawn_eviction_task(Duration::from_secs(60));

    // Auth middleware — applied only to /query, not health/ready probes.
    // When auth_disabled is true, pass an empty token so the middleware skips auth.
    let service_token = if config.auth_disabled {
        String::new()
    } else {
        config.service_token.clone()
    };

    // Clone token for estimate-cost middleware (each move closure needs its own copy)
    let estimate_cost_token = service_token.clone();

    // Main API router
    let app = Router::new()
        .route(
            "/query",
            post(handle_query).layer(axum::middleware::from_fn(move |req, next| {
                let token = service_token.clone();
                async move { require_bearer_token(req, next, &token).await }
            })),
        )
        .route(
            "/estimate-cost",
            post(handle_estimate_cost).layer(axum::middleware::from_fn(move |req, next| {
                let token = estimate_cost_token.clone();
                async move { require_bearer_token(req, next, &token).await }
            })),
        )
        .route("/_health", get(health_handler))
        .route("/_ready", get(readiness_handler))
        // Limit request body to 512 KB to prevent multi-MB SQL strings from
        // consuming excessive memory during hashing, EXPLAIN, and forwarding.
        .layer(DefaultBodyLimit::max(512_000))
        .with_state(state.clone());

    // Metrics router (separate port)
    let metrics_router = common_metrics::setup_metrics_routes(Router::new());

    // Lifecycle manager for graceful shutdown
    let manager = lifecycle::Manager::builder("clickhouse-gateway")
        .with_trap_signals(true)
        .with_prestop_check(true)
        .with_health_poll_interval(Duration::from_secs(2))
        .build();

    let guard = manager.monitor_background();

    // Bind listeners
    let listener = tokio::net::TcpListener::bind(&bind_addr)
        .await
        .expect("could not bind main port");
    tracing::info!("listening on {}", listener.local_addr().unwrap());

    let metrics_listener = tokio::net::TcpListener::bind(&metrics_addr)
        .await
        .expect("could not bind metrics port");
    tracing::info!(
        "metrics listening on {}",
        metrics_listener.local_addr().unwrap()
    );

    // Serve metrics on a separate task
    tokio::spawn(async move {
        axum::serve(metrics_listener, metrics_router.into_make_service())
            .await
            .expect("metrics server failed");
    });

    // Serve main API — use tokio::select! so the lifecycle shutdown signal
    // can interrupt the server (axum::serve blocks forever otherwise).
    tokio::select! {
        result = axum::serve(listener, app) => {
            if let Err(e) = result {
                tracing::error!(error = %e, "server failed");
            }
        }
        result = guard.wait() => {
            match result {
                Ok(()) => tracing::info!("Lifecycle shutdown triggered, stopping server"),
                Err(e) => tracing::warn!("Lifecycle monitor reported: {e}"),
            }
        }
    }
    tracing::info!("Shutdown complete");
}

async fn health_handler() -> axum::http::StatusCode {
    axum::http::StatusCode::OK
}

async fn readiness_handler() -> axum::http::StatusCode {
    // Check for prestop shutdown file (k8s rolling deployment pattern)
    if std::path::Path::new("/tmp/shutdown").exists() {
        return axum::http::StatusCode::SERVICE_UNAVAILABLE;
    }
    axum::http::StatusCode::OK
}
