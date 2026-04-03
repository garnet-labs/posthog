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
#   3. Set up NVMe instance store for Docker
#   4. Call `bin/sandbox create <branch> --no-attach` (same code path as local)
#
set -euo pipefail
exec > /var/log/sandbox-boot.log 2>&1

SECONDS=0
log() { echo "==> [${SECONDS}s] $*"; }

log "Cloud sandbox boot starting at $(date)"

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
log "Joining Tailscale network..."
tailscale up \
    --authkey="$TAILSCALE_AUTH_KEY" \
    --hostname="$SANDBOX_HOSTNAME" \
    --ssh
log "Tailscale joined as $SANDBOX_HOSTNAME"

# --- SSH authorized keys ---
log "Writing SSH authorized keys..."
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
log "Writing Claude Code auth..."
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
log "Setting up NVMe instance store..."

# Auto-detect the NVMe instance store device (not the root EBS).
ROOT_DEV=$(lsblk -no PKNAME "$(findmnt -n -o SOURCE /)" | head -1)
log "Root device: $ROOT_DEV"
log "Available NVMe devices: $(ls /dev/nvme*n1 2>/dev/null || echo 'none')"

NVME_DEV=""
for dev in /dev/nvme*n1; do
    name=$(basename "$dev")
    if [ "$name" != "$ROOT_DEV" ] && [ -b "$dev" ]; then
        NVME_DEV="$dev"
        break
    fi
done

if [ -z "$NVME_DEV" ]; then
    log "WARNING: No NVMe instance store found, staying on EBS"
else
    log "Found NVMe instance store: $NVME_DEV"
    log "NVMe device size: $(lsblk -no SIZE "$NVME_DEV")"

    mkfs.ext4 -F -L nvme-docker "$NVME_DEV"
    mkdir -p /mnt/nvme
    mount "$NVME_DEV" /mnt/nvme
    log "NVMe mounted at /mnt/nvme ($(df -h /mnt/nvme | tail -1 | awk '{print $2}') total)"

    mkdir -p /mnt/nvme/docker

    # Extract pre-built Docker data from the AMI archive to NVMe.
    # One sequential EBS read (~6GB compressed) is much faster than
    # copying 200k small files (throughput-bound vs IOPS-bound).
    if [ -f /var/cache/docker-data.tar.zst ]; then
        log "Found Docker cache archive: $(du -h /var/cache/docker-data.tar.zst | cut -f1)"
        log "Stopping Docker..."
        systemctl stop docker.socket docker
        log "Extracting Docker cache to NVMe..."
        tar -C /mnt/nvme/docker -I 'zstd -T0' -xf /var/cache/docker-data.tar.zst
        log "Extracted $(du -sh /mnt/nvme/docker | cut -f1) to NVMe"
        rm -rf /var/lib/docker
        ln -s /mnt/nvme/docker /var/lib/docker
        log "Symlinked /var/lib/docker -> /mnt/nvme/docker"
        systemctl start docker
        log "Docker restarted on NVMe ($NVME_DEV)"
    else
        log "No Docker cache archive at /var/cache/docker-data.tar.zst, using NVMe for fresh Docker"
        log "Contents of /var/cache/: $(ls -la /var/cache/ | head -20)"
        systemctl stop docker.socket docker
        rm -rf /var/lib/docker
        ln -s /mnt/nvme/docker /var/lib/docker
        systemctl start docker
        log "Docker started fresh on NVMe"
    fi

    log "Docker info: $(docker info --format '{{.DockerRootDir}}, Images: {{.Images}}, Driver: {{.Driver}}')"
fi

# --- Pre-populate sandbox config to skip interactive prompts ---
log "Pre-populating sandbox config..."
SANDBOX_CONFIG_DIR="/home/ubuntu/.posthog-sandboxes"
mkdir -p "$SANDBOX_CONFIG_DIR"
echo '{"jetbrains": null}' > "$SANDBOX_CONFIG_DIR/config.json"
chown -R ubuntu:ubuntu "$SANDBOX_CONFIG_DIR"

# --- Create sandbox using the standard local flow ---
log "Creating sandbox via bin/sandbox create..."
cd "$REPO_DIR"
sudo -u ubuntu HOME=/home/ubuntu git fetch origin --quiet
sudo -u ubuntu HOME=/home/ubuntu python3 bin/sandbox create "$SANDBOX_BRANCH" --no-attach

log "Cloud sandbox boot complete at $(date)"
log "Total boot time: ${SECONDS}s"
log "Tailscale hostname: $SANDBOX_HOSTNAME"
log "PostHog will be available at http://$SANDBOX_HOSTNAME:48001 once healthy"
