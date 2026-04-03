#!/usr/bin/env bash
#
# Build a pre-baked AMI for cloud sandboxes.
#
# No SSH or IAM instance profile required -- all provisioning happens via
# cloud-init user data. The script launches an instance, polls its console
# output for a completion marker, then snapshots it as an AMI.
#
# What the AMI contains:
#   - Ubuntu 24.04 x86_64
#   - Docker Engine + Docker Compose
#   - Tailscale (installed, not joined)
#   - PostHog repo at master HEAD
#   - Sandbox Docker image pre-built
#   - All Docker Compose images pre-pulled
#   - Postgres + ClickHouse pre-migrated
#
# At boot (on top of the AMI):
#   - Tailscale joins the network
#   - git fetch + checkout branch
#   - docker compose up (incremental deps + migrations)
#
# Usage:
#   ./build-ami.sh
#
# Environment variables:
#   AWS_PROFILE                (required — AWS CLI profile with EC2 access)
#   SANDBOX_SECURITY_GROUP     (required — security group with outbound access)
#   SANDBOX_SUBNET_ID          (required — subnet with internet access)
#   AWS_REGION                 (default: us-east-1)
#   BUILD_INSTANCE_TYPE        (default: m6i.2xlarge)
#   AWS_KEY_NAME               (optional, for SSH debug access)
#   DOCKERHUB_USER             (optional — Docker Hub username for authenticated pulls)
#   DOCKERHUB_TOKEN            (optional — Docker Hub access token)
#
set -euo pipefail

# --- Configuration ---
REGION="${AWS_REGION:-us-east-1}"
INSTANCE_TYPE="${BUILD_INSTANCE_TYPE:-m6id.2xlarge}"
VOLUME_SIZE=40
KEY_NAME="${AWS_KEY_NAME:-}"
BUILD_BRANCH="${BUILD_BRANCH:-}"
SECURITY_GROUP="${SANDBOX_SECURITY_GROUP:-}"
SUBNET_ID="${SANDBOX_SUBNET_ID:-}"

if [ -z "$SECURITY_GROUP" ]; then
    echo "ERROR: SANDBOX_SECURITY_GROUP is required"
    exit 1
fi
if [ -z "$SUBNET_ID" ]; then
    echo "ERROR: SANDBOX_SUBNET_ID is required"
    exit 1
fi

# Find latest Ubuntu 24.04 x86_64 AMI
BASE_AMI=$(aws ec2 describe-images \
    --region "$REGION" \
    --owners 099720109477 \
    --filters \
        "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
        "Name=state,Values=available" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
    --output text)

echo "==> Base AMI: $BASE_AMI"
echo "==> Region: $REGION"
echo "==> Instance type: $INSTANCE_TYPE"

# --- Build the user-data script ---
# This runs on the instance as root via cloud-init. When done, it writes
# a marker to the serial console so the local script can detect completion.
# No IAM permissions needed — no self-tagging.

USER_DATA=$(cat << 'USERDATA_EOF'
#!/usr/bin/env bash
set -euo pipefail
exec > /var/log/sandbox-ami-build.log 2>&1

SECONDS=0
log() { echo "==> [${SECONDS}s] $*"; }

# Write status markers to the serial console so the local build script
# can poll via `aws ec2 get-console-output`. Regular output goes to the
# log file (via the exec redirect above), but /dev/ttyS0 bypasses that.
build_status() {
    echo "===SANDBOX_BUILD_STATUS=$1===" > /dev/ttyS0 2>/dev/null || true
}

# On any error, dump the last 30 lines of the log to the serial console
# so the local polling script can see what went wrong.
trap 'build_status "failed"; echo "=== LAST 30 LINES ===" > /dev/ttyS0 2>/dev/null; tail -30 /var/log/sandbox-ami-build.log > /dev/ttyS0 2>/dev/null' ERR

build_status "provisioning"

# --- Set up NVMe instance store for Docker (if available) ---
# m6id instances have a local NVMe SSD. Using it for Docker builds
# avoids EBS IOPS bottlenecks during image builds and pnpm installs.
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

USE_NVME=false
if [ -n "$NVME_DEV" ]; then
    log "Found NVMe instance store: $NVME_DEV ($(lsblk -no SIZE "$NVME_DEV"))"
    mkfs.ext4 -F -L nvme-docker "$NVME_DEV"
    mkdir -p /mnt/nvme
    mount "$NVME_DEV" /mnt/nvme
    log "NVMe mounted at /mnt/nvme ($(df -h /mnt/nvme | tail -1 | awk '{print $2}') total)"
    USE_NVME=true
else
    log "No NVMe instance store found, building on EBS"
fi

# --- Install Docker ---
log "Installing Docker..."
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg zstd
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
usermod -aG docker ubuntu
log "Docker installed"

# Point Docker at NVMe if available — all builds run on fast local storage
if [ "$USE_NVME" = true ]; then
    log "Docker data before move: $(du -sh /var/lib/docker 2>/dev/null | cut -f1 || echo 'empty')"
    systemctl stop docker.socket docker
    mkdir -p /mnt/nvme/docker
    if [ -n "$(ls -A /var/lib/docker 2>/dev/null)" ]; then
        mv /var/lib/docker/* /mnt/nvme/docker/
        log "Moved Docker data to NVMe"
    else
        log "No Docker data to move (fresh install)"
    fi
    rm -rf /var/lib/docker
    ln -s /mnt/nvme/docker /var/lib/docker
    log "Symlinked /var/lib/docker -> /mnt/nvme/docker"
    systemctl start docker
    log "Docker restarted on NVMe"
fi

# --- Install Tailscale ---
log "Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sh
systemctl enable tailscaled
log "Tailscale installed"

# --- Clone PostHog repo ---
log "Cloning PostHog repo..."
build_status "cloning-repo"
cd /home/ubuntu
sudo -u ubuntu git clone https://github.com/PostHog/posthog.git
cd posthog
if [ -n "__BUILD_BRANCH__" ] && [ "__BUILD_BRANCH__" != "__" ]; then
    log "Checking out branch: __BUILD_BRANCH__"
    sudo -u ubuntu git fetch origin "__BUILD_BRANCH__"
    sudo -u ubuntu git checkout "__BUILD_BRANCH__"
fi
log "Repo ready at $(git rev-parse --short HEAD)"

# --- Docker Hub auth (avoids rate limiting) ---
if [ -n "__DOCKERHUB_USER__" ] && [ "__DOCKERHUB_USER__" != "__" ]; then
    log "Logging into Docker Hub as __DOCKERHUB_USER__..."
    sudo -u ubuntu sg docker -c "echo __DOCKERHUB_TOKEN__ | docker login -u __DOCKERHUB_USER__ --password-stdin"
    log "Docker Hub login complete"
fi

# --- Build database cache (same command as local) ---
log "Building database cache..."
build_status "building-cache"
apt-get install -y -qq python3-yaml
sudo -u ubuntu sg docker -c "python3 bin/sandbox rebuild-cache"
log "Database cache built"

# --- Archive Docker data for fast NVMe restore at boot ---
# At boot, cloud-init extracts this single archive to NVMe instead of
# copying 200k small files from EBS (throughput-bound vs IOPS-bound).
log "Archiving Docker data..."
build_status "archiving"
log "Docker data size: $(du -sh /var/lib/docker | cut -f1)"
systemctl stop docker.socket docker
tar -C /var/lib/docker -I 'zstd -T0 -3' -cf /var/cache/docker-data.tar.zst .
log "Archive created: $(du -h /var/cache/docker-data.tar.zst | cut -f1)"
# Remove loose Docker files — only the archive is needed in the AMI snapshot.
# This makes the snapshot smaller and faster to initialize from S3.
rm -rf /var/lib/docker
mkdir -p /var/lib/docker
log "Loose Docker files removed"

# If we used NVMe, unmount it — it won't be in the AMI snapshot
if [ "$USE_NVME" = true ]; then
    umount /mnt/nvme
    log "NVMe unmounted"
fi

# --- Clean up for snapshotting ---
log "Cleaning up for snapshot..."

apt-get clean
rm -rf /var/lib/apt/lists/*
rm -rf /tmp/*
rm -f /home/ubuntu/.docker/config.json
cloud-init clean --logs

build_status "complete"
log "AMI build complete! Total time: ${SECONDS}s"

# Stop the instance to signal completion to the local script.
# The local script detects "stopped" state as the success signal,
# which is far more reliable than polling console output.
shutdown -h now
USERDATA_EOF
)

# Inject build branch if specified
if [ -n "$BUILD_BRANCH" ]; then
    USER_DATA=$(echo "$USER_DATA" | sed "s|__BUILD_BRANCH__|$BUILD_BRANCH|g")
else
    USER_DATA=$(echo "$USER_DATA" | sed 's|__BUILD_BRANCH__||g')
fi

# Inject Docker Hub credentials if specified
DOCKERHUB_USER="${DOCKERHUB_USER:-}"
DOCKERHUB_TOKEN="${DOCKERHUB_TOKEN:-}"
USER_DATA=$(echo "$USER_DATA" | sed "s|__DOCKERHUB_USER__|$DOCKERHUB_USER|g")
USER_DATA=$(echo "$USER_DATA" | sed "s|__DOCKERHUB_TOKEN__|$DOCKERHUB_TOKEN|g")

# Base64 encode the user data
USER_DATA_B64=$(echo "$USER_DATA" | base64 -w 0 2>/dev/null || echo "$USER_DATA" | base64)

# --- Launch build instance ---
# No IAM instance profile — the instance doesn't need AWS API access.
# Status is communicated via serial console markers instead of EC2 tags.
RUN_ARGS=(
    --region "$REGION"
    --image-id "$BASE_AMI"
    --instance-type "$INSTANCE_TYPE"
    --user-data "$USER_DATA_B64"
    --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$VOLUME_SIZE,VolumeType=gp3,Encrypted=true}"
    --metadata-options "HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=2"
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=sandbox-ami-builder},{Key=sandbox,Value=true},{Key=sandbox-ami-builder,Value=true}]"
    --security-group-ids "$SECURITY_GROUP"
    --subnet-id "$SUBNET_ID"
    --instance-initiated-shutdown-behavior stop
)

if [ -n "$KEY_NAME" ]; then
    RUN_ARGS+=(--key-name "$KEY_NAME")
fi

INSTANCE_ID=$(aws ec2 run-instances \
    "${RUN_ARGS[@]}" \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "==> Build instance: $INSTANCE_ID"

cleanup() {
    echo "==> Terminating build instance $INSTANCE_ID..."
    aws ec2 terminate-instances --region "$REGION" --instance-ids "$INSTANCE_ID" > /dev/null 2>&1 || true
}
trap cleanup EXIT

# --- Wait for the instance to stop ---
# The user-data script calls `shutdown -h now` on success. We wait for
# the instance to reach "stopped" state — this is far more reliable than
# polling the EC2 console output API (which has multi-minute cache lag).
# Console output is still checked for progress updates and error details.
echo "==> Waiting for provisioning to complete (this takes 15-20 min)..."
echo "    Instance: $INSTANCE_ID"
echo "    The instance will stop itself when done."
echo ""

TIMEOUT=3600  # 60 minutes
ELAPSED=0
INTERVAL=30
LAST_STATUS=""

while [ $ELAPSED -lt $TIMEOUT ]; do
    # Check instance state
    STATE=$(aws ec2 describe-instances \
        --region "$REGION" \
        --instance-ids "$INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].State.Name' \
        --output text 2>/dev/null) || STATE="unknown"

    if [ "$STATE" = "stopped" ] || [ "$STATE" = "stopping" ]; then
        echo "  [$((ELAPSED / 60))m] Instance is $STATE — build complete!"
        # Wait for fully stopped if still stopping
        if [ "$STATE" = "stopping" ]; then
            aws ec2 wait instance-stopped --region "$REGION" --instance-ids "$INSTANCE_ID"
        fi
        break
    fi

    if [ "$STATE" = "terminated" ] || [ "$STATE" = "shutting-down" ]; then
        echo "ERROR: Instance was terminated unexpectedly (state: $STATE)"
        exit 1
    fi

    # Best-effort progress from console output (may be cached/delayed)
    CONSOLE=$(aws ec2 get-console-output \
        --region "$REGION" \
        --instance-id "$INSTANCE_ID" \
        --query 'Output' \
        --output text 2>/dev/null) || CONSOLE=""
    STATUS=$(echo "$CONSOLE" | grep -o '===SANDBOX_BUILD_STATUS=[a-z-]*===' | tail -1 | sed 's/===SANDBOX_BUILD_STATUS=//;s/===//' || echo "")

    if [ "$STATUS" = "failed" ]; then
        echo "ERROR: Build failed!"
        echo "$CONSOLE" | grep -A 100 "LAST 30 LINES" | head -40
        exit 1
    fi

    if [ -n "$STATUS" ] && [ "$STATUS" != "$LAST_STATUS" ]; then
        echo "  [$((ELAPSED / 60))m] Status: $STATUS"
        LAST_STATUS="$STATUS"
    elif [ -z "$STATUS" ]; then
        echo "  [$((ELAPSED / 60))m] Waiting for console output..."
    else
        echo "  [$((ELAPSED / 60))m] ($STATUS)"
    fi

    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "ERROR: Build timed out after $((TIMEOUT / 60)) minutes."
    echo "Last console output:"
    CONSOLE=$(aws ec2 get-console-output \
        --region "$REGION" \
        --instance-id "$INSTANCE_ID" \
        --query 'Output' \
        --output text 2>/dev/null) || CONSOLE=""
    echo "$CONSOLE" | tail -30
    exit 1
fi

DATE=$(date +%Y%m%d-%H%M%S)
AMI_NAME="cloud-sandbox-$DATE"

echo "==> Creating AMI: $AMI_NAME..."
AMI_ID=$(aws ec2 create-image \
    --region "$REGION" \
    --instance-id "$INSTANCE_ID" \
    --name "$AMI_NAME" \
    --description "PostHog cloud sandbox - built $DATE" \
    --tag-specifications "ResourceType=image,Tags=[{Key=sandbox-ami,Value=true},{Key=Name,Value=$AMI_NAME}]" \
    --query 'ImageId' \
    --output text)

echo "==> Waiting for AMI to be available (100GB snapshot, may take 15-20 min)..."
# Default waiter: 40 attempts × 15s = 10 min, which isn't enough for a 100GB EBS snapshot.
# Bump to 80 attempts (~20 min).
AWS_MAX_ATTEMPTS=80 aws ec2 wait image-available --region "$REGION" --image-ids "$AMI_ID"

echo ""
echo "=== AMI Build Complete ==="
echo "AMI ID: $AMI_ID"
echo "AMI Name: $AMI_NAME"
