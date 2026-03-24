#!/bin/bash
set -e

# =============================================================================
# Root phase — runs as UID 0.
# Creates the sandbox user, writes system config, starts sshd, then re-execs
# this script as the sandbox user via gosu.
# =============================================================================
if [ "$(id -u)" = "0" ] && [ "${SANDBOX_UID:-1000}" != "0" ]; then
    SUID="${SANDBOX_UID:-1000}"
    SGID="${SANDBOX_GID:-1000}"
    SANDBOX_HOME=/tmp/sandbox-home

    # Create a passwd/group/shadow entry for the sandbox user so tools like
    # git, whoami, and sshd resolve the UID correctly.
    if ! getent passwd "$SUID" > /dev/null 2>&1; then
        echo "sandbox:x:$SUID:$SGID:sandbox:$SANDBOX_HOME:/bin/bash" >> /etc/passwd
        getent group "$SGID" > /dev/null 2>&1 || echo "sandbox:x:$SGID:" >> /etc/group
        echo "sandbox:*:19000:0:99999:7:::" >> /etc/shadow
    fi

    # Create directories owned by the sandbox user.
    mkdir -p "$SANDBOX_HOME" /tmp/sandbox-cache
    chown "$SUID:$SGID" "$SANDBOX_HOME" /tmp/sandbox-cache

    # Export the full environment for SSH/IDE sessions.
    # Docker Compose env vars are only inherited by PID 1's children; SSH
    # sessions need them via PAM (/etc/environment) and login shells (profile.d).
    {
        env | grep -vE '^(HOSTNAME|TERM|SHELL|PWD|SHLVL|_|OLDPWD|HOME|USER|LOGNAME)='
        echo "HOME=$SANDBOX_HOME"
        echo "UV_CACHE_DIR=/cache/uv"
        echo "UV_LINK_MODE=copy"
        echo "XDG_CACHE_HOME=/tmp/sandbox-cache"
        echo "CARGO_TARGET_DIR=/cache/cargo-target"
        echo "npm_config_store_dir=/cache/pnpm"
        echo "COREPACK_ENABLE_AUTO_PIN=0"
        echo "COREPACK_ENABLE_DOWNLOAD_PROMPT=0"
    } | tee /etc/environment | sed 's/^/export /' > /etc/profile.d/sandbox-env.sh

    # Start sshd for IDE remote access (IntelliJ, VSCode Remote-SSH, etc.).
    if [ -s /tmp/sandbox-authorized-keys ]; then
        mkdir -p "$SANDBOX_HOME/.ssh"
        cp /tmp/sandbox-authorized-keys "$SANDBOX_HOME/.ssh/authorized_keys"
        chmod 700 "$SANDBOX_HOME/.ssh"
        chmod 600 "$SANDBOX_HOME/.ssh/authorized_keys"
        chown -R "$SUID:$SGID" "$SANDBOX_HOME/.ssh"
        /usr/sbin/sshd -p 2222 -o PidFile=/tmp/sshd.pid \
            -o PasswordAuthentication=no -o PermitRootLogin=no
        echo "==> sshd listening on port 2222"
    fi

    # Copy Claude Code auth from read-only mounts so it can write to ~/.claude.
    mkdir -p "$SANDBOX_HOME/.claude"
    cp -r /tmp/claude-auth/. "$SANDBOX_HOME/.claude/" 2>/dev/null || true
    cp /tmp/claude-auth.json "$SANDBOX_HOME/.claude.json" 2>/dev/null || true
    chown -R "$SUID:$SGID" "$SANDBOX_HOME"

    # Re-exec this script as the sandbox user.
    exec gosu "$SUID:$SGID" "$0" "$@"
fi

# =============================================================================
# User phase — runs as the sandbox UID via gosu.
# Everything that touches the worktree or caches runs here so files stay
# owned by the host user.
# =============================================================================
export HOME=/tmp/sandbox-home
export UV_CACHE_DIR=/cache/uv
export UV_LINK_MODE=copy
export XDG_CACHE_HOME=/tmp/sandbox-cache
export COREPACK_ENABLE_AUTO_PIN=0
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
export CARGO_TARGET_DIR=/cache/cargo-target
export npm_config_store_dir=/cache/pnpm
mkdir -p "$CARGO_TARGET_DIR"

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
sed -i "s|http://localhost:8234|${JS_URL}|g" posthog/utils.py
sed -i "s|:8234\"|:${JS_URL##*:}\"|g" posthog/utils.py
sed -i "s|origin: 'http://localhost:8234'|origin: process.env.JS_URL \|\| 'http://localhost:8234',\n            hmr: process.env.JS_URL ? { clientPort: parseInt(process.env.JS_URL.split(':').pop()) } : undefined|g" frontend/vite.config.ts
sed -i 's/"passThroughEnv": \["SKIP_TYPEGEN", "COREPACK_ENABLE_DOWNLOAD_PROMPT", "SSL_CERT_FILE"\]/"passThroughEnv": ["SKIP_TYPEGEN", "COREPACK_ENABLE_DOWNLOAD_PROMPT", "SSL_CERT_FILE", "JS_URL"]/g' turbo.json
# Add SESSION_COOKIE_NAME env var support if not present (no-op after merge).
grep -q 'SESSION_COOKIE_NAME.*get_from_env' posthog/settings/web.py || \
    sed -i '/^CSRF_COOKIE_NAME/i SESSION_COOKIE_NAME = get_from_env("SESSION_COOKIE_NAME", "sessionid")' posthog/settings/web.py
# --- END PRE-MERGE WORKAROUND ---

echo "==> Installing Python dependencies..."
uv sync --no-editable

# Make hogli available — normally done by flox on-activate.sh
ln -sfn /workspace/bin/hogli /cache/python/bin/hogli

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

echo "==> Generating mprocs config..."
# Seed intents on first boot; on restart, reuse the saved config.
mkdir -p .posthog/.generated
if [ ! -f .posthog/.generated/mprocs.yaml ] || ! grep -q "^_posthog:" .posthog/.generated/mprocs.yaml; then
    echo "    Seeding intents: ${SANDBOX_INTENTS:-product_analytics}"
    {
        echo "_posthog:"
        echo "  intents:"
        IFS=',' read -ra _intents <<< "${SANDBOX_INTENTS:-product_analytics}"
        for _intent in "${_intents[@]}"; do
            echo "  - ${_intent}"
        done
        echo "procs: {}"
    } > .posthog/.generated/mprocs.yaml
fi
hogli dev:generate 2>/dev/null || true

echo "==> Starting PostHog via mprocs in tmux..."
rm -f /workspace/bin/start.lock

exec tmux -L sandbox new-session -s posthog "bin/start"
