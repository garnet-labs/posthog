#!/bin/bash
set -e

cd /workspace

# --- PRE-MERGE WORKAROUND (delete this block after merging to master) ---
# The sandbox modifies several bin/ scripts and posthog/utils.py. Branches
# that don't have those changes yet will fail to boot. This block overlays
# the sandbox-aware versions from the Docker image onto the worktree.
# Once this PR is merged, every branch inherits the changes and this
# block does nothing useful (cp overwrites with identical files, sed is a no-op).
echo "==> Applying sandbox script overlays..."
cp /usr/local/share/sandbox/bin/wait-for-docker    bin/wait-for-docker
cp /usr/local/share/sandbox/bin/mprocs.yaml        bin/mprocs.yaml
cp /usr/local/share/sandbox/bin/start-backend      bin/start-backend
cp /usr/local/share/sandbox/bin/start-rust-service bin/start-rust-service
cp /usr/local/share/sandbox/posthog/management/commands/sandbox_migrate.py posthog/management/commands/sandbox_migrate.py
cp /usr/local/share/sandbox/nodejs/package.json    nodejs/package.json
cp /usr/local/share/sandbox/rust/cyclotron-node/package.json rust/cyclotron-node/package.json
# Fix hardcoded Vite dev server port in older branches (no-op after merge).
sed -i "s|http://localhost:8234|${JS_URL}|g" posthog/utils.py
# Add SESSION_COOKIE_NAME env var support if not present (no-op after merge).
grep -q 'SESSION_COOKIE_NAME.*get_from_env' posthog/settings/web.py || \
    sed -i '/^CSRF_COOKIE_NAME/i SESSION_COOKIE_NAME = get_from_env("SESSION_COOKIE_NAME", "sessionid")' posthog/settings/web.py
# --- END PRE-MERGE WORKAROUND ---

# When running as a non-root UID (the default — see docker-compose.sandbox.yml),
# HOME and cache dirs point to unwritable locations. Redirect to /tmp.
export HOME=/tmp/sandbox-home
export PATH="/usr/local/cargo/bin:$PATH"

export UV_CACHE_DIR=/cache/uv
export UV_LINK_MODE=copy
export UV_PROJECT_ENVIRONMENT=/usr/local/
export XDG_CACHE_HOME=/tmp/sandbox-cache
export COREPACK_ENABLE_AUTO_PIN=0
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
mkdir -p "$HOME" "$UV_CACHE_DIR" "$XDG_CACHE_HOME"
# Copy Claude Code auth from read-only mounts so it can write to ~/.claude
mkdir -p "$HOME/.claude"
cp -r /tmp/claude-auth/. "$HOME/.claude/" 2>/dev/null || true
cp /tmp/claude-auth.json "$HOME/.claude.json" 2>/dev/null || true

# Point Rust builds at the shared cargo-target volume (native ext4, not host-mounted).
# This avoids the VirtioFS overhead on macOS for the ~7GB of small-file random I/O
# that Rust compilation produces, and caches compiled deps across sandboxes.
export CARGO_TARGET_DIR=/cache/cargo-target
mkdir -p "$CARGO_TARGET_DIR"

# Point pnpm at the shared store volume (mounted at /cache/pnpm).
# This is a content-addressable cache — all sandboxes benefit from each other's installs.
# pnpm reads store-dir from npm_config_store_dir env var.
export npm_config_store_dir=/cache/pnpm

echo "==> Installing Python dependencies..."
uv sync --no-editable

# Make hogli available — normally done by flox on-activate.sh
ln -sfn /workspace/bin/hogli /usr/local/bin/hogli

echo "==> Installing Node dependencies..."
# CI=1 suppresses interactive prompts. --no-frozen-lockfile is needed because
# the pre-merge overlay may update package.json files that don't match the
# worktree's lockfile. GIT_DIR works around the worktree's .git file pointing
# to the host's .git/worktrees/ dir (not mounted in the container) — pnpm
# needs a working git for git-based dependencies (e.g. uWebSockets.js).
git init -q /tmp/sandbox-git
GIT_DIR=/tmp/sandbox-git CI=1 pnpm install --no-frozen-lockfile

echo "==> Running database migrations..."
python manage.py sandbox_migrate

echo "==> Downloading GeoIP database..."
bin/download-mmdb

# Generate demo data if the demo user doesn't exist yet (test@posthog.com / 12345678).
# When database volumes are pre-populated from cache (see bin/sandbox), the user
# already exists and this is skipped. Checking via SQL avoids a Django cold start.
if psql -h db -U posthog -d posthog -tAc "SELECT 1 FROM posthog_user WHERE email='test@posthog.com' LIMIT 1" 2>/dev/null | grep -q 1; then
    echo "==> Demo data already present, skipping generation."
else
    echo "==> Generating demo data (first boot)..."
    python manage.py generate_demo_data
fi

echo "==> Pre-creating Kafka topics..."
# librdkafka consumers set allowAutoTopicCreation=false in metadata requests,
# so Redpanda won't auto-create topics despite auto_create_topics_enabled=true.
# In normal dev, ClickHouse Kafka engine tables or the plugin server create these
# topics first. In a fresh sandbox volume nothing has, so we create them explicitly.
for topic in clickhouse_events_json exceptions_ingestion; do
    rpk topic describe "$topic" --brokers kafka:9092 >/dev/null 2>&1 \
        || rpk topic create "$topic" --brokers kafka:9092 -p 1 -r 1
done

echo "==> Starting PostHog via mprocs in tmux..."
# mprocs needs a real TTY, so we wrap bin/start in a tmux session.
# tmux -L <name> starts a fresh server that inherits our full environment.
# exec replaces this process so the container stays alive as long as tmux does.
# Use `sandbox shell <branch>` to attach and see the mprocs UI.
rm -f /workspace/bin/start.lock

exec tmux -L sandbox new-session -s posthog "bin/start"
