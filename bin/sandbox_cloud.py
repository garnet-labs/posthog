"""Cloud sandbox management — EC2 instances with Tailscale networking."""

from __future__ import annotations

import os
import sys
import json
import time
import shutil
import subprocess
import webbrowser
from pathlib import Path

from _sandbox_lib import (
    BUILD_CACHE_TEMPLATE,
    CLOUD_CONFIG_FILE,
    CLOUD_INIT_TEMPLATE,
    PORT_BASE,
    error,
    fatal,
    info,
    run,
    slugify,
    success,
    warn,
)


def _load_cloud_config() -> dict:
    """Load cloud sandbox config from ~/.posthog-sandboxes/cloud-config.json."""
    try:
        return json.loads(CLOUD_CONFIG_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cloud_config(config: dict) -> None:
    CLOUD_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CLOUD_CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")


def _ensure_cloud_config() -> dict:
    """Ensure cloud config exists with required fields. Prompt if missing."""
    config = _load_cloud_config()
    changed = False

    # Migrate from old AMI-based config
    if "ami_id" in config:
        info("Migrating cloud config: removing ami_id (no longer needed)")
        del config["ami_id"]
        changed = True

    if "s3_bucket" not in config:
        val = input("S3 bucket for Docker cache [posthog-sandbox-cache]: ").strip() or "posthog-sandbox-cache"
        config["s3_bucket"] = val
        changed = True
    if "s3_key" not in config:
        val = input("S3 key for Docker cache archive [docker-data.tar.zst]: ").strip() or "docker-data.tar.zst"
        config["s3_key"] = val
        changed = True
    if "security_group_id" not in config:
        val = input("Security group ID: ").strip()
        if not val:
            fatal("Security group ID is required.")
        config["security_group_id"] = val
        changed = True
    if "subnet_id" not in config:
        val = input("Subnet ID (with internet access): ").strip()
        if not val:
            fatal("Subnet ID is required.")
        config["subnet_id"] = val
        changed = True
    if "region" not in config:
        config["region"] = input("AWS region [us-east-1]: ").strip() or "us-east-1"
        changed = True
    if "aws_profile" not in config:
        config["aws_profile"] = input("AWS CLI profile name [default]: ").strip() or "default"
        changed = True

    if changed:
        _save_cloud_config(config)

    return config


def _cloud_hostname(owner: str, branch: str) -> str:
    """Generate a unique Tailscale hostname for a cloud sandbox.

    Includes a random suffix so recreating a sandbox for the same branch
    doesn't collide with stale Tailscale nodes from previous instances.
    """
    import secrets

    slug = slugify(branch)
    suffix = secrets.token_hex(3)  # 6 hex chars
    hostname = f"sandbox-{owner}-{slug}-{suffix}"
    # Tailscale hostnames max 63 chars
    if len(hostname) > 63:
        hostname = hostname[:63]
    return hostname


def _aws(config: dict, *args: str, capture: bool = True) -> subprocess.CompletedProcess:
    """Run an aws CLI command with the configured profile and region."""
    cmd = [
        "aws",
        "--region",
        config["region"],
        "--profile",
        config["aws_profile"],
        "--output",
        "json",
        *args,
    ]
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=capture,
            text=capture,
        )
    except FileNotFoundError:
        fatal(
            "AWS CLI not found. Install it: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        )
    except subprocess.CalledProcessError as e:
        # Re-raise with a cleaner message — the generic handler in main()
        # would show the full command including --profile and --region.
        aws_args = " ".join(args)
        error(f"aws {aws_args} failed (exit {e.returncode})")
        for line in (e.stderr or "").strip().splitlines():
            print(f"  {line}", file=sys.stderr)
        sys.exit(1)


def _cloud_get_owner() -> str:
    """Get the current user's identity for sandbox ownership."""
    result = subprocess.run(
        ["git", "config", "user.email"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        # Use the part before @ as the owner
        email = result.stdout.strip()
        return email.split("@")[0].replace(".", "-")
    return os.environ.get("USER", "unknown")


def _cloud_find_instance(config: dict, branch: str) -> dict | None:
    """Find a cloud sandbox instance by branch tag."""
    owner = _cloud_get_owner()
    result = _aws(
        config,
        "ec2",
        "describe-instances",
        "--filters",
        f"Name=tag:sandbox:owner,Values={owner}",
        f"Name=tag:sandbox:branch,Values={branch}",
        "Name=instance-state-name,Values=running,stopped,pending,stopping",
    )
    data = json.loads(result.stdout)
    for reservation in data.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            return instance
    return None


def _cloud_list_instances(config: dict) -> list[dict]:
    """List all cloud sandbox instances for the current user."""
    owner = _cloud_get_owner()
    result = _aws(
        config,
        "ec2",
        "describe-instances",
        "--filters",
        f"Name=tag:sandbox:owner,Values={owner}",
        "Name=tag:sandbox,Values=true",
        "Name=instance-state-name,Values=running,stopped,pending,stopping",
    )
    data = json.loads(result.stdout)
    instances = []
    for reservation in data.get("Reservations", []):
        instances.extend(reservation.get("Instances", []))
    return instances


def _cloud_get_tag(instance: dict, key: str) -> str:
    """Get a tag value from an EC2 instance."""
    for tag in instance.get("Tags", []):
        if tag["Key"] == key:
            return tag["Value"]
    return ""


def _cloud_render_user_data(
    branch: str,
    owner: str,
    hostname: str,
    tailscale_key: str,
    ssh_keys: str,
    claude_credentials: str,
    claude_settings: str,
    claude_json: str,
    s3_archive_url: str,
) -> str:
    """Render the cloud-init script with sandbox-specific values.

    Returns base64-encoded gzip data — cloud-init auto-detects the gzip
    magic bytes and decompresses before executing.  This keeps us well
    under the 16 KB AWS user-data limit.
    """
    import gzip
    import base64

    template = CLOUD_INIT_TEMPLATE.read_text()

    # Base64-encode values that may contain quotes or special chars
    # to avoid breaking the bash script. Cloud-init decodes them.
    replacements = {
        "__SANDBOX_BRANCH__": branch,
        "__SANDBOX_OWNER__": owner,
        "__SANDBOX_HOSTNAME__": hostname,
        "__TAILSCALE_AUTH_KEY_B64__": base64.b64encode(tailscale_key.encode()).decode() if tailscale_key else "",
        "__SSH_AUTHORIZED_KEYS_B64__": base64.b64encode(ssh_keys.encode()).decode() if ssh_keys else "",
        "__CLAUDE_CREDENTIALS_B64__": base64.b64encode(claude_credentials.encode()).decode()
        if claude_credentials
        else "",
        "__CLAUDE_SETTINGS_B64__": base64.b64encode(claude_settings.encode()).decode() if claude_settings else "",
        "__CLAUDE_JSON_B64__": base64.b64encode(claude_json.encode()).decode() if claude_json else "",
        "__S3_ARCHIVE_URL_B64__": base64.b64encode(s3_archive_url.encode()).decode() if s3_archive_url else "",
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    compressed = gzip.compress(template.encode(), compresslevel=9)
    return base64.b64encode(compressed).decode()


def _cloud_get_tailscale_key(config: dict) -> str:
    """Get the Tailscale auth key from config or Secrets Manager."""
    # Check local config first
    if "tailscale_auth_key" in config:
        return config["tailscale_auth_key"]

    # Try Secrets Manager
    secret_arn = config.get("tailscale_secret_arn")
    if secret_arn:
        result = _aws(config, "secretsmanager", "get-secret-value", "--secret-id", secret_arn)
        data = json.loads(result.stdout)
        return data["SecretString"]

    # Prompt and save
    key = input("Tailscale auth key (reusable + ephemeral): ").strip()
    if not key:
        fatal(
            "Tailscale auth key is required.\n  Generate a reusable + ephemeral key at https://login.tailscale.com/admin/settings/keys\n  (Ephemeral ensures nodes auto-remove when instances terminate.)"
        )
    config["tailscale_auth_key"] = key
    _save_cloud_config(config)
    return key


def _cloud_gather_auth() -> tuple[str, str, str, str]:
    """Gather SSH keys and Claude auth for the cloud sandbox."""
    # SSH keys
    ssh_dir = Path.home() / ".ssh"
    ssh_keys = []
    if ssh_dir.is_dir():
        for pub in ssh_dir.glob("*.pub"):
            ssh_keys.append(pub.read_text().strip())
    ssh_keys_str = "\n".join(ssh_keys)

    if not ssh_keys:
        fatal(
            "No SSH public keys found in ~/.ssh/.\n"
            "  You need at least one SSH key to connect to the sandbox.\n"
            "  Generate one with: ssh-keygen -t ed25519"
        )

    # Claude auth
    claude_dir = Path.home() / ".claude"
    claude_credentials = ""
    claude_settings = ""
    claude_json = ""

    creds_file = claude_dir / ".credentials.json"
    if creds_file.exists():
        claude_credentials = creds_file.read_text().strip()
    elif sys.platform == "darwin":
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            claude_credentials = result.stdout.strip()

    if not claude_credentials:
        warn("No Claude Code credentials found. Claude Code won't work on the sandbox until you log in manually.")

    settings_file = claude_dir / "settings.json"
    if settings_file.exists():
        claude_settings = settings_file.read_text().strip()

    claude_json_file = Path.home() / ".claude.json"
    if claude_json_file.exists():
        # Only include auth-relevant fields — the full file can exceed
        # the 16KB AWS user-data limit (projects history is ~10KB alone).
        CLAUDE_JSON_KEEP = {"oauthAccount", "userID", "hasCompletedOnboarding"}
        full = json.loads(claude_json_file.read_text())
        claude_json = json.dumps({k: v for k, v in full.items() if k in CLAUDE_JSON_KEEP})

    return ssh_keys_str, claude_credentials, claude_settings, claude_json


def _cloud_discover_ubuntu_ami(config: dict) -> str:
    """Find the latest Ubuntu 24.04 x86_64 AMI from Canonical."""
    info("Discovering latest Ubuntu 24.04 AMI...")
    result = _aws(
        config,
        "ec2",
        "describe-images",
        "--owners",
        "099720109477",
        "--filters",
        "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*",
        "Name=state,Values=available",
        "--query",
        "sort_by(Images, &CreationDate)[-1].ImageId",
        "--output",
        "text",
    )
    ami_id = result.stdout.strip()
    if not ami_id or ami_id == "None":
        fatal("Could not find Ubuntu 24.04 AMI. Check your AWS region and credentials.")
    info(f"  Using AMI: {ami_id}")
    return ami_id


def _cloud_generate_presigned_url(config: dict) -> str:
    """Generate a pre-signed S3 URL for the Docker cache archive."""
    bucket = config["s3_bucket"]
    key = config["s3_key"]
    s3_uri = f"s3://{bucket}/{key}"

    # Verify the object exists
    result = _aws(config, "s3", "ls", s3_uri)
    if not result.stdout.strip():
        fatal(f"Docker cache archive not found at {s3_uri}\n  Upload it first: bin/sandbox cloud upload-cache")

    info(f"Generating pre-signed URL for {s3_uri}...")
    result = _aws(
        config,
        "s3",
        "presign",
        s3_uri,
        "--expires-in",
        "3600",
    )
    url = result.stdout.strip()
    if not url:
        fatal("Failed to generate pre-signed S3 URL")
    return url


def cmd_cloud_create(branch: str) -> None:
    config = _ensure_cloud_config()
    owner = _cloud_get_owner()
    hostname = _cloud_hostname(owner, branch)

    # Check if sandbox already exists
    existing = _cloud_find_instance(config, branch)
    if existing:
        state = existing["State"]["Name"]
        instance_id = existing["InstanceId"]
        error(f"Sandbox for '{branch}' already exists ({instance_id}, state: {state})")
        if state == "running":
            print(f"  Connect:    sandbox cloud shell {branch}")
        print(f"  Destroy it: sandbox cloud destroy {branch}")
        sys.exit(1)

    info(f"Creating cloud sandbox for '{branch}'...")
    info(f"  Tailscale hostname: {hostname}")

    # Auto-discover Ubuntu AMI (no custom AMI needed)
    ami_id = _cloud_discover_ubuntu_ami(config)

    # Generate pre-signed S3 URL for Docker cache
    s3_archive_url = _cloud_generate_presigned_url(config)

    tailscale_key = _cloud_get_tailscale_key(config)
    ssh_keys, claude_credentials, claude_settings, claude_json = _cloud_gather_auth()

    user_data = _cloud_render_user_data(
        branch=branch,
        owner=owner,
        hostname=hostname,
        tailscale_key=tailscale_key,
        ssh_keys=ssh_keys,
        claude_credentials=claude_credentials,
        claude_settings=claude_settings,
        claude_json=claude_json,
        s3_archive_url=s3_archive_url,
    )

    # AWS user data limit is 16KB (decoded size, i.e. the gzip blob).
    import base64 as _b64

    user_data_bytes = len(_b64.b64decode(user_data))
    info(f"  User data size: {user_data_bytes} bytes (gzip compressed, limit 16384)")
    if user_data_bytes > 16384:
        fatal(
            f"User data is {user_data_bytes} bytes, exceeding AWS 16KB limit.\n"
            "  This usually means Claude settings or SSH keys are too large.\n"
            "  Check ~/.claude/settings.json and ~/.ssh/*.pub"
        )

    result = _aws(
        config,
        "ec2",
        "run-instances",
        "--image-id",
        ami_id,
        "--instance-type",
        "m6id.2xlarge",
        "--subnet-id",
        config["subnet_id"],
        "--security-group-ids",
        config["security_group_id"],
        "--block-device-mappings",
        "DeviceName=/dev/sda1,Ebs={VolumeSize=100,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}",
        "--metadata-options",
        "HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=2",
        "--user-data",
        user_data,
        "--tag-specifications",
        json.dumps(
            [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": f"sandbox-{owner}-{slugify(branch)}"},
                        {"Key": "sandbox", "Value": "true"},
                        {"Key": "sandbox:owner", "Value": owner},
                        {"Key": "sandbox:branch", "Value": branch},
                        {"Key": "sandbox:hostname", "Value": hostname},
                        {"Key": "sandbox:created", "Value": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                    ],
                }
            ]
        ),
    )

    data = json.loads(result.stdout)
    instance_id = data["Instances"][0]["InstanceId"]
    info(f"  Instance: {instance_id}")

    info("Waiting for instance to start...")
    _aws(config, "ec2", "wait", "instance-running", "--instance-ids", instance_id)

    info(f"Instance {instance_id} running. Waiting for Tailscale SSH...")

    # Poll until we can SSH in via Tailscale
    ssh_base = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "LogLevel=ERROR",
        f"ubuntu@{hostname}",
    ]
    deadline = time.monotonic() + 180  # 3 min for Tailscale to join
    while time.monotonic() < deadline:
        result = run(ssh_base + ["true"], check=False, capture=True)
        if result.returncode == 0:
            break
        time.sleep(5)
    else:
        fatal(
            f"Timed out waiting for Tailscale SSH on {hostname}.\n"
            f"  Instance: {instance_id}\n"
            f"  Try manually: ssh ubuntu@{hostname}"
        )

    success(f"SSH connected to {hostname}")
    info("Tailing boot log (Ctrl-C to detach, sandbox keeps booting)...")
    print()

    # Tail the boot log until sandbox creation finishes, then attach.
    # We use tail -f and watch for the completion marker.
    boot_done = False
    try:
        proc = subprocess.Popen(
            ssh_base + ["tail -n +1 -f /var/log/sandbox-boot.log"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            if "Cloud sandbox boot complete" in line:
                boot_done = True
                proc.terminate()
                proc.wait()
                break
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        info("\nDetached from boot log. Sandbox is still booting.")
        print(f"  Reattach:  sandbox cloud logs {branch}")
        print(f"  Shell:     sandbox cloud shell {branch}")
        return

    if not boot_done:
        fatal(f"Boot log ended without completion marker.\n  Check logs: sandbox cloud logs {branch}")

    print()
    success(f"Cloud sandbox ready for '{branch}'")

    # Open browser in background, then attach to mprocs (like local flow)
    url = f"http://{hostname}:{PORT_BASE}"
    subprocess.Popen(
        [sys.executable, "-c", f"import webbrowser; webbrowser.open({url!r})"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    info("Attaching to mprocs... (detach with Ctrl-b d)")
    os.execvp(
        "ssh",
        [
            "ssh",
            "-A",
            "-t",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"ubuntu@{hostname}",
            f"cd /home/ubuntu/posthog && python3 bin/sandbox shell {branch}",
        ],
    )


def cmd_cloud_destroy(branch: str) -> None:
    config = _ensure_cloud_config()
    instance = _cloud_find_instance(config, branch)
    if not instance:
        fatal(f"No cloud sandbox found for branch '{branch}'")

    instance_id = instance["InstanceId"]
    hostname = _cloud_get_tag(instance, "sandbox:hostname")

    warn(f"Destroying cloud sandbox for '{branch}' (instance {instance_id})...")

    _aws(config, "ec2", "terminate-instances", "--instance-ids", instance_id)
    success("Instance terminating.")

    if hostname:
        info(f"Tailscale node '{hostname}' will auto-remove after ~30-60 min offline (ephemeral key).")


def cmd_cloud_list() -> None:
    config = _ensure_cloud_config()
    instances = _cloud_list_instances(config)

    if not instances:
        print("No cloud sandboxes found. Create one with: sandbox cloud create <branch>")
        return

    print(f"{'BRANCH':<40} {'STATE':<12} {'INSTANCE':<22} HOSTNAME")
    print(f"{'------':<40} {'-----':<12} {'--------':<22} --------")

    for inst in instances:
        branch = _cloud_get_tag(inst, "sandbox:branch")
        hostname = _cloud_get_tag(inst, "sandbox:hostname")
        state = inst["State"]["Name"]
        instance_id = inst["InstanceId"]
        print(f"{branch:<40} {state:<12} {instance_id:<22} {hostname}")


def cmd_cloud_shell(branch: str) -> None:
    config = _ensure_cloud_config()
    instance = _cloud_find_instance(config, branch)
    if not instance:
        fatal(f"No cloud sandbox found for branch '{branch}'")
    if instance["State"]["Name"] != "running":
        fatal(f"Sandbox is not running (state: {instance['State']['Name']})")

    hostname = _cloud_get_tag(instance, "sandbox:hostname")
    if not hostname:
        fatal("No Tailscale hostname found for this sandbox")

    # SSH to the host, then use bin/sandbox shell (same as local).
    # UserKnownHostsFile=/dev/null avoids polluting known_hosts — Tailscale
    # handles host identity, and the host key changes on every EC2 instance.
    os.execvp(
        "ssh",
        [
            "ssh",
            "-A",  # Forward SSH agent for git auth
            "-t",  # Force TTY allocation
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"ubuntu@{hostname}",
            f"cd /home/ubuntu/posthog && python3 bin/sandbox shell {branch}",
        ],
    )


def cmd_cloud_open(branch: str) -> None:
    config = _ensure_cloud_config()
    instance = _cloud_find_instance(config, branch)
    if not instance:
        fatal(f"No cloud sandbox found for branch '{branch}'")
    if instance["State"]["Name"] != "running":
        fatal(f"Sandbox is not running (state: {instance['State']['Name']})")

    hostname = _cloud_get_tag(instance, "sandbox:hostname")
    url = f"http://{hostname}:{PORT_BASE}"
    info(f"Opening {url}...")
    webbrowser.open(url)


def cmd_cloud_logs(branch: str) -> None:
    config = _ensure_cloud_config()
    instance = _cloud_find_instance(config, branch)
    if not instance:
        fatal(f"No cloud sandbox found for branch '{branch}'")

    hostname = _cloud_get_tag(instance, "sandbox:hostname")
    if not hostname:
        fatal("No Tailscale hostname found for this sandbox")

    slug = slugify(branch)
    container = f"sandbox-{slug}-app-1"

    # Show the boot log (one-shot), then follow the app container logs.
    # We use `docker logs` directly rather than `docker compose logs` because
    # the compose file requires env vars that aren't set in the SSH session.
    os.execvp(
        "ssh",
        [
            "ssh",
            "-t",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"ubuntu@{hostname}",
            f"echo '=== Boot log ===' && cat /var/log/sandbox-boot.log 2>/dev/null; "
            f"echo '\\n=== App container logs ===' && docker logs -f {container}",
        ],
    )


def cmd_cloud_code(branch: str) -> None:
    config = _ensure_cloud_config()
    instance = _cloud_find_instance(config, branch)
    if not instance:
        fatal(f"No cloud sandbox found for branch '{branch}'")
    if instance["State"]["Name"] != "running":
        fatal(f"Sandbox is not running (state: {instance['State']['Name']})")

    hostname = _cloud_get_tag(instance, "sandbox:hostname")

    code_cmd = shutil.which("code")
    if not code_cmd:
        info("VSCode 'code' CLI not found on PATH.")
        info(f"Connect manually: code --remote ssh-remote+ubuntu@{hostname} /workspace")
        return

    info(f"Opening VSCode Remote-SSH to {hostname}...")
    subprocess.Popen([code_cmd, "--remote", f"ssh-remote+ubuntu@{hostname}", "/home/ubuntu/posthog"])


def cmd_cloud_idea(branch: str) -> None:
    config = _ensure_cloud_config()
    instance = _cloud_find_instance(config, branch)
    if not instance:
        fatal(f"No cloud sandbox found for branch '{branch}'")
    if instance["State"]["Name"] != "running":
        fatal(f"Sandbox is not running (state: {instance['State']['Name']})")

    hostname = _cloud_get_tag(instance, "sandbox:hostname")

    from urllib.parse import quote

    uri = (
        f"jetbrains-gateway://connect#type=ssh&deploy=false"
        f"&host={hostname}&port=2222&user=sandbox"
        f"&projectPath={quote('/workspace')}"
        f"&idePath={quote('/opt/idea')}"
    )

    for cmd_name in ["gateway", "jetbrains-gateway", "xdg-open", "open"]:
        cmd = shutil.which(cmd_name)
        if cmd:
            info(f"Opening JetBrains Gateway for sandbox at {hostname}...")
            subprocess.Popen([cmd, uri])
            return

    info("Could not auto-open Gateway.")
    info(f"Connect manually: File -> Remote Development -> SSH")
    info(f"  Host: {hostname}  Port: 2222  User: sandbox")
    info(f"  Project: /workspace")


def cmd_cloud_upload_cache() -> None:
    """Archive local Docker data and upload to S3 for cloud sandbox boot."""
    config = _ensure_cloud_config()
    bucket = config["s3_bucket"]
    key = config["s3_key"]
    s3_uri = f"s3://{bucket}/{key}"
    archive_path = "/tmp/docker-data.tar.zst"

    info("Archiving Docker data for cloud sandbox cache...")

    # Check Docker is running and has images
    result = run(["docker", "info", "--format", "{{.Images}}"], capture=True, check=False)
    if result.returncode != 0:
        fatal("Docker is not running. Start Docker first.")
    image_count = result.stdout.strip()
    info(f"  Docker has {image_count} images")

    # Stop all sandbox containers first for a cleaner snapshot
    info("Stopping sandbox containers...")
    run(["docker", "compose", "-p", "sandbox-cache-init", "down", "-t", "0"], check=False, capture=True)

    # Archive Docker data from inside a container. This works on both Linux
    # (direct access) and macOS (OrbStack/Docker Desktop — the container sees
    # the real /var/lib/docker inside the Linux VM).
    info("Creating archive (this may take a few minutes)...")
    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            "/var/lib/docker:/docker:ro",
            "-v",
            "/tmp:/output",
            "alpine",
            "sh",
            "-c",
            "apk add --no-cache zstd > /dev/null 2>&1 && "
            "tar cf - -C /docker . | zstd -T0 -3 > /output/docker-data.tar.zst",
        ],
    )

    # The archive is in /tmp inside the Docker VM. On Linux, that's the host /tmp.
    # On macOS (OrbStack/Docker Desktop), we need to copy it out.
    if sys.platform == "darwin":
        info("Copying archive from Docker VM to host...")
        run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                "/tmp:/input:ro",
                "-v",
                f"{Path(archive_path).parent}:/output",
                "alpine",
                "cp",
                "/input/docker-data.tar.zst",
                "/output/docker-data.tar.zst",
            ],
        )

    archive_size = Path(archive_path).stat().st_size
    info(f"  Archive size: {archive_size / (1024 * 1024):.0f} MB")

    info(f"Uploading to {s3_uri}...")
    _aws(config, "s3", "cp", archive_path, s3_uri, capture=False)

    info("Cleaning up temp file...")
    Path(archive_path).unlink(missing_ok=True)

    success(f"Docker cache uploaded to {s3_uri}")
    info(f"  Archive size: {archive_size / (1024 * 1024):.0f} MB")
    info("  Cloud sandboxes will download this at boot time.")


def _cloud_export_credentials(config: dict) -> str:
    """Export current AWS credentials as shell env vars for embedding in user data."""
    result = subprocess.run(
        [
            "aws",
            "configure",
            "export-credentials",
            "--profile",
            config["aws_profile"],
            "--format",
            "process",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fatal(
            "Could not export AWS credentials. Make sure you're logged in:\n"
            f"  aws sso login --profile {config['aws_profile']}"
        )
    creds = json.loads(result.stdout)
    # Build shell export lines
    lines = [
        f'export AWS_ACCESS_KEY_ID="{creds["AccessKeyId"]}"',
        f'export AWS_SECRET_ACCESS_KEY="{creds["SecretAccessKey"]}"',
    ]
    if creds.get("SessionToken"):
        lines.append(f'export AWS_SESSION_TOKEN="{creds["SessionToken"]}"')
    return "\n".join(lines)


def cmd_cloud_build_cache() -> None:
    """Launch an EC2 instance to build the sandbox cache and upload to S3."""
    import base64

    config = _ensure_cloud_config()
    ami_id = _cloud_discover_ubuntu_ami(config)

    # Export current AWS credentials for the build instance to upload to S3
    info("Exporting AWS credentials for build instance...")
    aws_creds_env = _cloud_export_credentials(config)

    # Render the build-cache user data template
    template = BUILD_CACHE_TEMPLATE.read_text()
    # Use the current branch so the build instance has local fixes
    current_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if current_branch == "HEAD":
        current_branch = ""  # detached HEAD, use master

    replacements = {
        "__AWS_CREDENTIALS_B64__": base64.b64encode(aws_creds_env.encode()).decode(),
        "__BUILD_BRANCH__": current_branch,
        "__S3_BUCKET__": config["s3_bucket"],
        "__S3_KEY__": config["s3_key"],
        "__AWS_REGION__": config["region"],
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    user_data = base64.b64encode(template.encode()).decode()

    info(f"Launching cache builder instance...")
    info(f"  S3 target: s3://{config['s3_bucket']}/{config['s3_key']}")

    result = _aws(
        config,
        "ec2",
        "run-instances",
        "--image-id",
        ami_id,
        "--instance-type",
        "m6id.2xlarge",
        "--subnet-id",
        config["subnet_id"],
        "--security-group-ids",
        config["security_group_id"],
        "--block-device-mappings",
        "DeviceName=/dev/sda1,Ebs={VolumeSize=40,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}",
        "--metadata-options",
        "HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=2",
        "--user-data",
        user_data,
        "--instance-initiated-shutdown-behavior",
        "stop",
        "--tag-specifications",
        json.dumps(
            [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": "sandbox-cache-builder"},
                        {"Key": "sandbox", "Value": "true"},
                        {"Key": "sandbox-cache-builder", "Value": "true"},
                    ],
                }
            ]
        ),
    )

    data = json.loads(result.stdout)
    instance_id = data["Instances"][0]["InstanceId"]
    info(f"  Instance: {instance_id}")
    info("Waiting for build to complete (instance stops itself when done)...")
    info("  This typically takes 15-20 minutes.")
    info(
        f"  SSH:  aws ec2-instance-connect ssh --instance-id {instance_id} "
        f"--connection-type eice --os-user ubuntu --profile {config['aws_profile']}"
    )
    info(f"  Logs: sudo tail -f /var/log/sandbox-build-cache.log")

    # Poll instance state — it stops itself on completion or failure
    timeout = 3600
    elapsed = 0
    interval = 30
    s3_uri = f"s3://{config['s3_bucket']}/{config['s3_key']}"
    while elapsed < timeout:
        state_result = _aws(
            config,
            "ec2",
            "describe-instances",
            "--instance-ids",
            instance_id,
            "--query",
            "Reservations[0].Instances[0].State.Name",
            "--output",
            "text",
        )
        state = state_result.stdout.strip()

        if state in ("stopped", "stopping", "terminated", "shutting-down"):
            if state == "stopping":
                time.sleep(30)
            # Check if the build succeeded by verifying S3 object
            info("Build instance stopped. Verifying S3 upload...")
            verify = _aws(config, "s3", "ls", s3_uri)
            if verify.stdout.strip():
                success("Cache built and uploaded successfully!")
                info(f"  {s3_uri}")
                parts = verify.stdout.strip().split()
                if len(parts) >= 3:
                    size_bytes = int(parts[2])
                    info(f"  Size: {size_bytes / (1024 * 1024):.0f} MB")
            else:
                error("Build failed — S3 object not found.")
                info(f"  Start instance to debug:")
                info(
                    f"    aws ec2 start-instances --instance-ids {instance_id} "
                    f"--profile {config['aws_profile']} --region {config['region']}"
                )
                info(f"  Then: sudo cat /var/log/sandbox-build-cache.log")
            # Clean up
            if state != "terminated":
                info(f"Terminating build instance...")
                _aws(config, "ec2", "terminate-instances", "--instance-ids", instance_id)
            return

        elapsed_min = elapsed // 60
        if elapsed_min > 0 and elapsed % 60 == 0:
            info(f"  [{elapsed_min}m] Instance state: {state}")

        time.sleep(interval)
        elapsed += interval

    # Timeout — terminate the instance
    error(f"Build timed out after {timeout // 60} minutes.")
    info(f"Terminating instance {instance_id}...")
    _aws(config, "ec2", "terminate-instances", "--instance-ids", instance_id)
    sys.exit(1)
