# This service uses the shared multi-stage Rust Dockerfile at rust/Dockerfile.
# Build with:
#   docker build -f rust/Dockerfile --build-arg BIN=clickhouse-gateway -t clickhouse-gateway rust/
#
# Alternatively, for a standalone build:

FROM rust:1.91-bookworm AS base
RUN cargo install --locked cargo-chef sccache@0.12.0
ENV RUSTC_WRAPPER=sccache SCCACHE_DIR=/sccache

FROM base AS planner
WORKDIR /app
COPY . .
RUN cargo chef prepare --recipe-path recipe.json --bin clickhouse-gateway

FROM base AS builder
WORKDIR /app
RUN apt-get update && apt-get install build-essential libssl-dev pkg-config cmake -y
COPY --from=planner /app/recipe.json recipe.json
RUN --mount=type=cache,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,target=$SCCACHE_DIR,sharing=locked \
    SCCACHE_NO_DAEMON=1 SCCACHE_START_SERVER=1 sccache 2>&1 & \
    cargo chef cook --release --recipe-path recipe.json --bin clickhouse-gateway && \
    sccache --show-stats
COPY . .
RUN --mount=type=cache,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,target=$SCCACHE_DIR,sharing=locked \
    SCCACHE_NO_DAEMON=1 SCCACHE_START_SERVER=1 sccache 2>&1 & \
    cargo build --release --bin clickhouse-gateway && \
    sccache --show-stats

FROM debian:bookworm-slim AS runtime
RUN apt-get update && \
    apt-get install -y --no-install-recommends libssl-dev ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
USER nobody
COPY --from=builder /app/target/release/clickhouse-gateway /usr/local/bin/clickhouse-gateway
ENTRYPOINT ["/usr/local/bin/clickhouse-gateway"]
