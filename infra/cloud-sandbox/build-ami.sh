#!/usr/bin/env bash
#
# Build a pre-baked AMI for cloud sandboxes.
#
# No SSH required -- all provisioning happens via cloud-init user data.
# The script launches an instance, waits for setup to complete (by polling
# an EC2 tag), then snapshots it as an AMI.
#
# What the AMI contains:
#   - Ubuntu 24.04 x86_64
#   - Docker Engine + Docker Compose
#   - Tailscale (installed, not joined)
#   - PostHog repo at master HEAD
#   - Sandbox Docker image pre-built
#   - All Docker Compose images pre-pulled
#   - Postgres + ClickHouse pre-migrated
#   - Auto-sleep cron installed
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
#   AWS_REGION                 (default: us-east-1)
#   BUILD_INSTANCE_TYPE        (default: m6i.2xlarge)
#   SANDBOX_SECURITY_GROUP     (from Terraform output)
#   SANDBOX_SUBNET_ID          (from Terraform output)
#   SANDBOX_INSTANCE_PROFILE   (default: cloud-sandbox)
#   AWS_KEY_NAME               (optional, for SSH debug access)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Configuration ---
REGION="${AWS_REGION:-us-east-1}"
INSTANCE_TYPE="${BUILD_INSTANCE_TYPE:-m6i.2xlarge}"
VOLUME_SIZE=100
KEY_NAME="${AWS_KEY_NAME:-}"
SECURITY_GROUP="${SANDBOX_SECURITY_GROUP:-}"
SUBNET_ID="${SANDBOX_SUBNET_ID:-}"
INSTANCE_PROFILE="${SANDBOX_INSTANCE_PROFILE:-cloud-sandbox}"

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
# This runs on the instance as root via cloud-init. It does all the setup,
# then tags the instance with build-status=complete so we know it's done.

# Read the auto-sleep script and embed it in the user data
AUTO_SLEEP_SCRIPT=$(cat "$SCRIPT_DIR/auto-sleep.sh")

USER_DATA=$(cat << 'USERDATA_EOF'
#!/usr/bin/env bash
set -euo pipefail
exec > /var/log/sandbox-ami-build.log 2>&1

INSTANCE_ID=$(ec2metadata --instance-id 2>/dev/null || \
    curl -sf -H "X-aws-ec2-metadata-token: $(curl -sf -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" \
    http://169.254.169.254/latest/meta-data/instance-id)
REGION=$(ec2metadata --availability-zone 2>/dev/null | sed 's/.$//' || \
    curl -sf -H "X-aws-ec2-metadata-token: $(curl -sf -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" \
    http://169.254.169.254/latest/meta-data/placement/region)

tag_status() {
    aws ec2 create-tags --region "$REGION" --resources "$INSTANCE_ID" \
        --tags "Key=build-status,Value=$1" || true
}

tag_status "provisioning"

# --- Install Docker ---
echo "==> Installing Docker..."
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg awscli
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
usermod -aG docker ubuntu

# --- Install Tailscale ---
echo "==> Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sh
systemctl enable tailscaled

# --- Install auto-sleep cron ---
echo "==> Installing auto-sleep cron..."
cat > /usr/local/bin/sandbox-auto-sleep.sh << 'AUTOSLEEP'
__AUTO_SLEEP_SCRIPT__
AUTOSLEEP
chmod +x /usr/local/bin/sandbox-auto-sleep.sh
echo "*/10 * * * * root /usr/local/bin/sandbox-auto-sleep.sh" > /etc/cron.d/sandbox-auto-sleep

# --- Clone PostHog repo ---
echo "==> Cloning PostHog repo..."
tag_status "cloning-repo"
cd /home/ubuntu
sudo -u ubuntu git clone https://github.com/PostHog/posthog.git
cd posthog

# --- Build sandbox Docker image + pull compose images ---
echo "==> Building sandbox image..."
tag_status "building-image"
sudo -u ubuntu docker build -f Dockerfile.sandbox -t posthog-sandbox:latest .

echo "==> Pulling compose images..."
tag_status "pulling-images"
sudo -u ubuntu docker compose -f docker-compose.sandbox.yml pull --ignore-buildable

# --- Create shared Docker volumes ---
echo "==> Creating Docker volumes..."
sudo -u ubuntu bash -c '
for vol in sandbox-uv-cache sandbox-pnpm-store sandbox-db-cache sandbox-cargo-target sandbox-intellij; do
    docker volume create "$vol"
done
for vol in sandbox-db-cache sandbox-cargo-target sandbox-intellij; do
    docker run --rm -v "$vol:/data" alpine chmod 777 /data
done
'

# --- Boot the stack and run migrations ---
echo "==> Booting stack for initial migration..."
tag_status "migrating"
cd /home/ubuntu/posthog

export COMPOSE_PROJECT_NAME=sandbox-cloud
export SANDBOX_PORT=8000
export SANDBOX_VITE_PORT=8234
export SANDBOX_SSH_PORT=2222
export SANDBOX_CODE=/home/ubuntu/posthog
export SANDBOX_GIT_DIR=/home/ubuntu/posthog/.git
export SANDBOX_UID=1000
export SANDBOX_GID=1000
export SANDBOX_MODE=cloud
export SANDBOX_CLAUDE_AUTH=/dev/null
export SANDBOX_CLAUDE_JSON=/dev/null
export SANDBOX_SSH_AUTHORIZED_KEYS=/dev/null
export SANDBOX_IDE_VOLUME=sandbox-intellij

sudo -u ubuntu -E docker compose -f docker-compose.sandbox.yml up -d

echo "==> Waiting for stack to be healthy..."
for i in $(seq 1 300); do
    if curl -sf http://localhost:8000/_health > /dev/null 2>&1; then
        echo "Stack is healthy!"
        break
    fi
    if [ "$i" -eq 300 ]; then
        echo "ERROR: Stack did not become healthy in time"
        sudo -u ubuntu docker compose -f docker-compose.sandbox.yml logs app --tail=50
        tag_status "failed"
        exit 1
    fi
    sleep 2
done

# Graceful stop -- ClickHouse and Kafka don't like hard kills
echo "==> Stopping stack..."
sudo -u ubuntu docker compose -f docker-compose.sandbox.yml stop

# --- Clean up for snapshotting ---
echo "==> Cleaning up..."
apt-get clean
rm -rf /var/lib/apt/lists/*
rm -rf /tmp/*
cloud-init clean --logs

tag_status "complete"
echo "==> AMI build provisioning complete!"
USERDATA_EOF

# Embed the auto-sleep script into the user data
USER_DATA="${USER_DATA//__AUTO_SLEEP_SCRIPT__/$AUTO_SLEEP_SCRIPT}"

# Base64 encode the user data
USER_DATA_B64=$(echo "$USER_DATA" | base64 -w 0 2>/dev/null || echo "$USER_DATA" | base64)

# --- Launch build instance ---
RUN_ARGS=(
    --region "$REGION"
    --image-id "$BASE_AMI"
    --instance-type "$INSTANCE_TYPE"
    --user-data "$USER_DATA_B64"
    --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$VOLUME_SIZE,VolumeType=gp3,Encrypted=true}"
    --metadata-options "HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=2"
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=sandbox-ami-builder},{Key=sandbox-ami-builder,Value=true},{Key=build-status,Value=starting}]"
)

if [ -n "$KEY_NAME" ]; then
    RUN_ARGS+=(--key-name "$KEY_NAME")
fi
if [ -n "$SECURITY_GROUP" ]; then
    RUN_ARGS+=(--security-group-ids "$SECURITY_GROUP")
fi
if [ -n "$SUBNET_ID" ]; then
    RUN_ARGS+=(--subnet-id "$SUBNET_ID")
fi
if [ -n "$INSTANCE_PROFILE" ]; then
    RUN_ARGS+=(--iam-instance-profile "Name=$INSTANCE_PROFILE")
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

# --- Poll for completion ---
echo "==> Waiting for provisioning to complete (this takes 15-20 min)..."
echo "    You can monitor progress via the build-status tag on instance $INSTANCE_ID"
echo "    Or view logs via SSM: aws ssm start-session --target $INSTANCE_ID"
echo ""

TIMEOUT=2400  # 40 minutes
ELAPSED=0
INTERVAL=30

while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(aws ec2 describe-tags \
        --region "$REGION" \
        --filters "Name=resource-id,Values=$INSTANCE_ID" "Name=key,Values=build-status" \
        --query 'Tags[0].Value' \
        --output text 2>/dev/null || echo "unknown")

    echo "  [$((ELAPSED / 60))m] Status: $STATUS"

    if [ "$STATUS" = "complete" ]; then
        break
    fi
    if [ "$STATUS" = "failed" ]; then
        echo "ERROR: Build failed. Check logs via SSM:"
        echo "  aws ssm start-session --target $INSTANCE_ID"
        # Don't exit -- the trap will terminate the instance
        exit 1
    fi

    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "ERROR: Build timed out after $((TIMEOUT / 60)) minutes."
    echo "Check logs via SSM: aws ssm start-session --target $INSTANCE_ID"
    exit 1
fi

# --- Stop the instance and create AMI ---
echo "==> Stopping instance for snapshot..."
aws ec2 stop-instances --region "$REGION" --instance-ids "$INSTANCE_ID" > /dev/null
aws ec2 wait instance-stopped --region "$REGION" --instance-ids "$INSTANCE_ID"

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

echo "==> Waiting for AMI to be available..."
aws ec2 wait image-available --region "$REGION" --image-ids "$AMI_ID"

echo "==> AMI ready: $AMI_ID ($AMI_NAME)"

# --- Clean up old AMIs (keep last 3) ---
echo "==> Cleaning up old AMIs..."
OLD_AMIS=$(aws ec2 describe-images \
    --region "$REGION" \
    --owners self \
    --filters "Name=tag:sandbox-ami,Values=true" \
    --query 'sort_by(Images, &CreationDate)[:-3].ImageId' \
    --output text)

for old_ami in $OLD_AMIS; do
    echo "  Deregistering $old_ami..."
    SNAPSHOTS=$(aws ec2 describe-images \
        --region "$REGION" \
        --image-ids "$old_ami" \
        --query 'Images[0].BlockDeviceMappings[*].Ebs.SnapshotId' \
        --output text)
    aws ec2 deregister-image --region "$REGION" --image-id "$old_ami"
    for snap in $SNAPSHOTS; do
        echo "  Deleting snapshot $snap..."
        aws ec2 delete-snapshot --region "$REGION" --snapshot-id "$snap" || true
    done
done

echo ""
echo "=== AMI Build Complete ==="
echo "AMI ID: $AMI_ID"
echo "AMI Name: $AMI_NAME"
echo ""
echo "Update the terragrunt.hcl with:"
echo "  ami_id = \"$AMI_ID\""
