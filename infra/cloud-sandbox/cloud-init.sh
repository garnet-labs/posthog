#!/usr/bin/env bash
#
# Cloud-init user data script for cloud sandboxes.
#
# This script runs ONCE at first boot on a STOCK Ubuntu 24.04 AMI.
# It's templated by bin/sandbox — placeholders like __SANDBOX_BRANCH__
# are replaced at launch time.
#
# Boot flow:
#   1. Install Tailscale + join network (enables SSH for debugging)
#   2. Write SSH keys + Claude auth
#   3. Install Docker, zstd, git, python3-yaml
#   4. Detect + format + mount NVMe instance store
#   5. Download docker-data.tar.zst from S3 (pre-signed URL)
#   6. Extract to NVMe, symlink /var/lib/docker
#   7. Start Docker
#   8. git clone PostHog repo to NVMe
#   9. git fetch + checkout branch, detach HEAD
#  10. bin/sandbox create <branch> --no-attach
#
set -euo pipefail
exec > /var/log/sandbox-boot.log 2>&1

SECONDS=0
log() { echo "==> [${SECONDS}s] $*"; }

# Write boot status on exit so the CLI can detect failure quickly.
BOOT_STATUS="failed"
cleanup() {
    log "Boot status: $BOOT_STATUS"
    echo "$BOOT_STATUS" > /var/log/sandbox-boot-status
}
trap cleanup EXIT

log "Cloud sandbox boot starting at $(date)"

# --- Variables (replaced by bin/sandbox at launch time) ---
SANDBOX_BRANCH="__SANDBOX_BRANCH__"
SANDBOX_OWNER="__SANDBOX_OWNER__"
SANDBOX_HOSTNAME="__SANDBOX_HOSTNAME__"
CLAUDE_CREDENTIALS_B64="__CLAUDE_CREDENTIALS_B64__"
CLAUDE_SETTINGS_B64="__CLAUDE_SETTINGS_B64__"
CLAUDE_JSON_B64="__CLAUDE_JSON_B64__"
S3_ARCHIVE_URL_B64="__S3_ARCHIVE_URL_B64__"
TAILSCALE_AUTH_KEY_B64="__TAILSCALE_AUTH_KEY_B64__"
SSH_AUTHORIZED_KEYS_B64="__SSH_AUTHORIZED_KEYS_B64__"

# Decode base64-encoded values (avoids shell-special chars breaking assignments)
S3_ARCHIVE_URL=""
if [ -n "$S3_ARCHIVE_URL_B64" ]; then
    S3_ARCHIVE_URL=$(echo "$S3_ARCHIVE_URL_B64" | base64 -d)
fi
TAILSCALE_AUTH_KEY=""
if [ -n "$TAILSCALE_AUTH_KEY_B64" ]; then
    TAILSCALE_AUTH_KEY=$(echo "$TAILSCALE_AUTH_KEY_B64" | base64 -d)
fi
SSH_AUTHORIZED_KEYS=""
if [ -n "$SSH_AUTHORIZED_KEYS_B64" ]; then
    SSH_AUTHORIZED_KEYS=$(echo "$SSH_AUTHORIZED_KEYS_B64" | base64 -d)
fi

REPO_DIR="/home/ubuntu/posthog"

# --- Install Tailscale (fast, enables SSH for debugging) ---
log "Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sh
systemctl enable tailscaled

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

# --- Install Docker, zstd, git ---
log "Installing Docker and dependencies..."
# Pin overlay2 storage driver to match the build-cache archive.
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'DAEMONJSON'
{
  "features": {
    "containerd-snapshotter": false
  },
  "storage-driver": "overlay2"
}
DAEMONJSON
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg zstd git python3-yaml
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
usermod -aG docker ubuntu

# Stop Docker immediately — we need to set up storage before it runs.
# apt auto-starts Docker, but we'll restart it after NVMe + S3 extract.
systemctl stop docker.socket docker
log "Docker installed (stopped for storage setup)"

# --- Set up NVMe instance store ---
log "Setting up NVMe instance store..."

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
    chown ubuntu:ubuntu /mnt/nvme
    log "NVMe mounted at /mnt/nvme ($(df -h /mnt/nvme | tail -1 | awk '{print $2}') total)"

    mkdir -p /mnt/nvme/docker
    rm -rf /var/lib/docker
    ln -s /mnt/nvme/docker /var/lib/docker
    log "Symlinked /var/lib/docker -> /mnt/nvme/docker"
fi

# --- Clone PostHog repo (background, overlaps with S3 download) ---
log "Cloning PostHog repo (background)..."
clone_repo() {
    if [ -n "$NVME_DEV" ]; then
        sudo -u ubuntu git clone https://github.com/PostHog/posthog.git /mnt/nvme/posthog
        ln -s /mnt/nvme/posthog "$REPO_DIR"
    else
        sudo -u ubuntu git clone https://github.com/PostHog/posthog.git "$REPO_DIR"
    fi
}
clone_repo &
CLONE_PID=$!

# --- Download and extract Docker cache from S3 ---
if [ -n "$S3_ARCHIVE_URL" ]; then
    log "Downloading Docker cache from S3..."
    DOWNLOAD_OK=false
    for attempt in 1 2 3; do
        if curl -fSL -o /tmp/docker-data.tar.zst "$S3_ARCHIVE_URL"; then
            DOWNLOAD_OK=true
            break
        fi
        log "Download attempt $attempt failed, retrying in 10s..."
        sleep 10
    done
    if [ "$DOWNLOAD_OK" = false ]; then
        log "ERROR: All download attempts failed"
        exit 1
    fi
    log "Downloaded $(du -h /tmp/docker-data.tar.zst | cut -f1)"

    log "Extracting Docker cache..."
    mkdir -p /var/lib/docker
    tar -C /var/lib/docker -I 'zstd -T0' -xf /tmp/docker-data.tar.zst
    log "Extracted $(du -sh /var/lib/docker | cut -f1) to Docker data dir"
    rm -f /tmp/docker-data.tar.zst
else
    log "WARNING: No S3 archive URL provided, Docker starts with no cached images"
fi

# --- Start Docker ---
systemctl start docker
log "Docker started"
log "Docker info: $(docker info --format '{{.DockerRootDir}}, Images: {{.Images}}, Driver: {{.Driver}}')"

# --- Wait for repo clone ---
log "Waiting for repo clone..."
wait $CLONE_PID || { log "ERROR: git clone failed"; exit 1; }
log "Repo cloned"

# --- Pre-populate sandbox config to skip interactive prompts ---
log "Pre-populating sandbox config..."
SANDBOX_CONFIG_DIR="/home/ubuntu/.posthog-sandboxes"
mkdir -p "$SANDBOX_CONFIG_DIR"
echo '{"jetbrains": null}' > "$SANDBOX_CONFIG_DIR/config.json"
chown -R ubuntu:ubuntu "$SANDBOX_CONFIG_DIR"

# --- Fetch branch and create worktree ---
log "Fetching branch $SANDBOX_BRANCH..."
cd "$REPO_DIR"
sudo -u ubuntu HOME=/home/ubuntu git fetch origin --quiet
sudo -u ubuntu HOME=/home/ubuntu git fetch origin "$SANDBOX_BRANCH" --quiet \
    || log "WARNING: fetch of $SANDBOX_BRANCH failed, will try with available refs"

# Detach HEAD to avoid "already checked out" errors
sudo -u ubuntu HOME=/home/ubuntu git checkout --detach HEAD

# Create worktree directly with git (posthog-worktree requires flox, not available on cloud)
# bin/sandbox create's find_worktree() will discover this and skip posthog-worktree.
WORKTREE_DIR="/home/ubuntu/.worktrees/posthog/$SANDBOX_BRANCH"
log "Creating worktree at $WORKTREE_DIR..."
sudo -u ubuntu HOME=/home/ubuntu mkdir -p "$(dirname "$WORKTREE_DIR")"
sudo -u ubuntu HOME=/home/ubuntu git worktree add "$WORKTREE_DIR" "$SANDBOX_BRANCH"

log "Creating sandbox via bin/sandbox create..."
cd "$WORKTREE_DIR"
sudo -u ubuntu HOME=/home/ubuntu sg docker -c "python3 bin/sandbox create '$SANDBOX_BRANCH' --no-attach"

BOOT_STATUS="complete"
log "Cloud sandbox boot complete at $(date)"
log "Total boot time: ${SECONDS}s"
log "Tailscale hostname: $SANDBOX_HOSTNAME"
log "PostHog will be available at http://$SANDBOX_HOSTNAME:48001 once healthy"
