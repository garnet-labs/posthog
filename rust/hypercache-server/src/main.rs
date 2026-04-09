use envconfig::Envconfig;
use tokio::signal;
use tracing::level_filters::LevelFilter;
use tracing_subscriber::fmt;
use tracing_subscriber::fmt::format::FmtSpan;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::{EnvFilter, Layer};

use hypercache_server::config::Config;

common_alloc::used!();

async fn shutdown() {
    let mut term = signal::unix::signal(signal::unix::SignalKind::terminate())
        .expect("failed to register SIGTERM handler");

    let mut interrupt = signal::unix::signal(signal::unix::SignalKind::interrupt())
        .expect("failed to register SIGINT handler");

    tokio::select! {
        _ = term.recv() => {},
        _ = interrupt.recv() => {},
    };

    tracing::info!("Shutting down gracefully...");
}

#[tokio::main]
async fn main() {
    let config = Config::init_from_env().expect("Invalid configuration:");

    let log_layer = {
        let base_layer = fmt::layer()
            .with_target(true)
            .with_thread_ids(true)
            .with_level(true);

        if config.debug {
            base_layer
                .with_span_events(FmtSpan::NEW | FmtSpan::CLOSE)
                .with_ansi(true)
                .with_filter(
                    EnvFilter::builder()
                        .with_default_directive(LevelFilter::INFO.into())
                        .from_env_lossy(),
                )
                .boxed()
        } else {
            base_layer
                .json()
                .with_span_list(false)
                .with_filter(
                    EnvFilter::builder()
                        .with_default_directive(LevelFilter::INFO.into())
                        .from_env_lossy(),
                )
                .boxed()
        }
    };

    tracing_subscriber::registry().with(log_layer).init();

    let listener = tokio::net::TcpListener::bind(config.address)
        .await
        .expect("could not bind port");

    hypercache_server::server::serve(config, listener, shutdown()).await;
}
