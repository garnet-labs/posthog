#!/usr/bin/env bash
#
# Cloud-init user data script for cloud sandboxes.
#
# This script runs ONCE at first boot only. It's templated by bin/sandbox —
# placeholders like __SANDBOX_BRANCH__ are replaced at launch time.
#
# What it does:
#   1. Join Tailscale network
#   2. Write SSH authorized keys + Claude auth
#   3. Call `bin/sandbox create <branch> --no-attach` (same code path as local)
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
CLAUDE_CREDENTIALS_B64="__CLAUDE_CREDENTIALS_B64__"
CLAUDE_SETTINGS_B64="__CLAUDE_SETTINGS_B64__"
CLAUDE_JSON_B64="__CLAUDE_JSON_B64__"

REPO_DIR="/home/ubuntu/posthog"

# --- Tailscale ---
echo "==> Joining Tailscale network..."
tailscale up \
    --authkey="$TAILSCALE_AUTH_KEY" \
    --hostname="$SANDBOX_HOSTNAME" \
    --ssh

# --- SSH authorized keys ---
echo "==> Writing SSH authorized keys..."
UBUNTU_SSH_DIR="/home/ubuntu/.ssh"
mkdir -p "$UBUNTU_SSH_DIR"
echo "$SSH_AUTHORIZED_KEYS" > "$UBUNTU_SSH_DIR/authorized_keys"
# Also write as a .pub file so _ssh_authorized_keys_path() finds them
echo "$SSH_AUTHORIZED_KEYS" > "$UBUNTU_SSH_DIR/cloud.pub"
chmod 700 "$UBUNTU_SSH_DIR"
chmod 600 "$UBUNTU_SSH_DIR/authorized_keys"
chmod 644 "$UBUNTU_SSH_DIR/cloud.pub"
chown -R ubuntu:ubuntu "$UBUNTU_SSH_DIR"

# --- Claude Code auth (written to ~/.claude/ where bin/sandbox expects it) ---
echo "==> Writing Claude Code auth..."
CLAUDE_AUTH_DIR="/home/ubuntu/.claude"
mkdir -p "$CLAUDE_AUTH_DIR"

if [ -n "$CLAUDE_CREDENTIALS_B64" ]; then
    echo "$CLAUDE_CREDENTIALS_B64" | base64 -d > "$CLAUDE_AUTH_DIR/.credentials.json"
fi
if [ -n "$CLAUDE_SETTINGS_B64" ]; then
    echo "$CLAUDE_SETTINGS_B64" | base64 -d > "$CLAUDE_AUTH_DIR/settings.json"
fi

if [ -n "$CLAUDE_JSON_B64" ]; then
    echo "$CLAUDE_JSON_B64" | base64 -d > "/home/ubuntu/.claude.json"
    chown ubuntu:ubuntu "/home/ubuntu/.claude.json"
fi

chown -R ubuntu:ubuntu "$CLAUDE_AUTH_DIR"

# --- Move Docker to NVMe for I/O performance ---
echo "==> Setting up NVMe instance store..."

# Auto-detect the NVMe instance store device (not the root EBS).
ROOT_DEV=$(lsblk -no PKNAME $(findmnt -n -o SOURCE /) | head -1)
NVME_DEV=""
for dev in /dev/nvme*n1; do
    name=$(basename "$dev")
    if [ "$name" != "$ROOT_DEV" ] && [ -b "$dev" ]; then
        NVME_DEV="$dev"
        break
    fi
done

if [ -z "$NVME_DEV" ]; then
    echo "==> WARNING: No NVMe instance store found, staying on EBS"
else
    echo "==> Found NVMe instance store: $NVME_DEV"
    mkfs.ext4 -L nvme-docker "$NVME_DEV"
    mkdir -p /mnt/nvme
    mount "$NVME_DEV" /mnt/nvme

    # Copy existing Docker data (images, volumes, build cache from AMI) to NVMe
    systemctl stop docker
    cp -a /var/lib/docker /mnt/nvme/docker
    rm -rf /var/lib/docker
    ln -s /mnt/nvme/docker /var/lib/docker
    systemctl start docker
    echo "==> Docker data moved to NVMe ($NVME_DEV)"
fi

# --- Pre-populate sandbox config to skip interactive prompts ---
echo "==> Pre-populating sandbox config..."
SANDBOX_CONFIG_DIR="/home/ubuntu/.posthog-sandboxes"
mkdir -p "$SANDBOX_CONFIG_DIR"
echo '{"jetbrains": null}' > "$SANDBOX_CONFIG_DIR/config.json"
chown -R ubuntu:ubuntu "$SANDBOX_CONFIG_DIR"

# --- Create sandbox using the standard local flow ---
echo "==> Creating sandbox via bin/sandbox create..."
cd "$REPO_DIR"
sudo -u ubuntu HOME=/home/ubuntu git fetch origin --quiet
sudo -u ubuntu HOME=/home/ubuntu python3 bin/sandbox create "$SANDBOX_BRANCH" --no-attach

echo "==> Cloud sandbox boot complete at $(date)"
echo "==> Tailscale hostname: $SANDBOX_HOSTNAME"
echo "==> PostHog will be available at http://$SANDBOX_HOSTNAME:48001 once healthy"
