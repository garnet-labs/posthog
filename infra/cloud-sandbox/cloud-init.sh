#!/usr/bin/env bash
#
# Cloud-init user data script for cloud sandboxes.
#
# This script runs at instance boot (both first boot and wake from sleep).
# It's templated by bin/sandbox — variables like SANDBOX_BRANCH are replaced
# at launch time.
#
# What it does:
#   1. Join Tailscale network
#   2. Write SSH authorized keys + Claude auth
#   3. Git fetch and checkout the target branch
#   4. Start docker compose
#
set -euo pipefail
exec > /var/log/sandbox-boot.log 2>&1

echo "==> Cloud sandbox boot starting at $(date)"

# --- Variables (replaced by bin/sandbox at launch time) ---
SANDBOX_BRANCH="__SANDBOX_BRANCH__"
SANDBOX_OWNER="__SANDBOX_OWNER__"
SANDBOX_HOSTNAME="__SANDBOX_HOSTNAME__"
TAILSCALE_AUTH_KEY="__TAILSCALE_AUTH_KEY__"
SSH_AUTHORIZED_KEYS="__SSH_AUTHORIZED_KEYS__"
CLAUDE_CREDENTIALS="__CLAUDE_CREDENTIALS__"
CLAUDE_SETTINGS="__CLAUDE_SETTINGS__"
CLAUDE_JSON="__CLAUDE_JSON__"

REPO_DIR="/home/ubuntu/posthog"

# --- Tailscale ---
echo "==> Joining Tailscale network..."
sudo tailscale up \
    --authkey="$TAILSCALE_AUTH_KEY" \
    --hostname="$SANDBOX_HOSTNAME" \
    --ssh

# --- SSH authorized keys ---
echo "==> Writing SSH authorized keys..."
UBUNTU_SSH_DIR="/home/ubuntu/.ssh"
mkdir -p "$UBUNTU_SSH_DIR"
echo "$SSH_AUTHORIZED_KEYS" > "$UBUNTU_SSH_DIR/authorized_keys"
chmod 700 "$UBUNTU_SSH_DIR"
chmod 600 "$UBUNTU_SSH_DIR/authorized_keys"
chown -R ubuntu:ubuntu "$UBUNTU_SSH_DIR"

# --- Claude Code auth ---
echo "==> Writing Claude Code auth..."
CLAUDE_AUTH_DIR="/home/ubuntu/.sandbox-claude-auth"
mkdir -p "$CLAUDE_AUTH_DIR"

if [ -n "$CLAUDE_CREDENTIALS" ] && [ "$CLAUDE_CREDENTIALS" != "__CLAUDE_CREDENTIALS__" ]; then
    echo "$CLAUDE_CREDENTIALS" > "$CLAUDE_AUTH_DIR/.credentials.json"
fi
if [ -n "$CLAUDE_SETTINGS" ] && [ "$CLAUDE_SETTINGS" != "__CLAUDE_SETTINGS__" ]; then
    echo "$CLAUDE_SETTINGS" > "$CLAUDE_AUTH_DIR/settings.json"
fi

CLAUDE_JSON_FILE="/dev/null"
if [ -n "$CLAUDE_JSON" ] && [ "$CLAUDE_JSON" != "__CLAUDE_JSON__" ]; then
    echo "$CLAUDE_JSON" > "/home/ubuntu/.sandbox-claude.json"
    CLAUDE_JSON_FILE="/home/ubuntu/.sandbox-claude.json"
fi

chown -R ubuntu:ubuntu "$CLAUDE_AUTH_DIR"

# --- Git fetch + checkout branch ---
echo "==> Fetching branch: $SANDBOX_BRANCH..."
cd "$REPO_DIR"
git fetch origin --quiet

# Check if the branch exists on remote
if git show-ref --verify --quiet "refs/remotes/origin/$SANDBOX_BRANCH" 2>/dev/null; then
    git checkout -B "$SANDBOX_BRANCH" "origin/$SANDBOX_BRANCH"
else
    # Branch doesn't exist on remote yet - create it from master
    git checkout -B "$SANDBOX_BRANCH" origin/master
fi

chown -R ubuntu:ubuntu "$REPO_DIR"

# --- Start Docker Compose ---
echo "==> Starting Docker Compose..."
cd "$REPO_DIR"

export COMPOSE_PROJECT_NAME=sandbox-cloud
export SANDBOX_PORT=8000
export SANDBOX_VITE_PORT=8234
export SANDBOX_SSH_PORT=2222
export SANDBOX_CODE="$REPO_DIR"
export SANDBOX_GIT_DIR="$REPO_DIR/.git"
export SANDBOX_UID=1000
export SANDBOX_GID=1000
export SANDBOX_MODE=cloud
export SANDBOX_CLAUDE_AUTH="$CLAUDE_AUTH_DIR"
export SANDBOX_CLAUDE_JSON="$CLAUDE_JSON_FILE"
export SANDBOX_SSH_AUTHORIZED_KEYS="$UBUNTU_SSH_DIR/authorized_keys"
export SANDBOX_IDE_VOLUME=sandbox-intellij

sudo -u ubuntu -E docker compose -f docker-compose.sandbox.yml up -d

echo "==> Cloud sandbox boot complete at $(date)"
echo "==> Tailscale hostname: $SANDBOX_HOSTNAME"
echo "==> PostHog will be available at http://$SANDBOX_HOSTNAME:8000 once healthy"
