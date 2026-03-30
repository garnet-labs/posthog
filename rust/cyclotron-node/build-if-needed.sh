#!/usr/bin/env bash
# Skip cyclotron cargo build when index.node is already up-to-date.
# Compares index.node mtime against source files, Cargo.toml, and Cargo.lock.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INDEX_NODE="$SCRIPT_DIR/index.node"

if [ ! -f "$INDEX_NODE" ]; then
    echo "cyclotron: index.node missing, building..."
    exec pnpm --filter=@posthog/cyclotron package
fi

# Find the newest source file across cyclotron-node and cyclotron-core
RUST_DIR="$(dirname "$SCRIPT_DIR")"
NEWEST_SOURCE=$(find \
    "$SCRIPT_DIR/src" \
    "$RUST_DIR/cyclotron-core/src" \
    "$SCRIPT_DIR/Cargo.toml" \
    "$RUST_DIR/cyclotron-core/Cargo.toml" \
    "$RUST_DIR/Cargo.toml" \
    "$RUST_DIR/Cargo.lock" \
    -type f \( -name '*.rs' -o -name 'Cargo.toml' -o -name 'Cargo.lock' \) \
    -newer "$INDEX_NODE" \
    -print -quit 2>/dev/null || true)

if [ -n "$NEWEST_SOURCE" ]; then
    echo "cyclotron: source changed ($NEWEST_SOURCE), rebuilding..."
    exec pnpm --filter=@posthog/cyclotron package
fi

echo "cyclotron: up to date, skipping build"
