# Cloud Sandbox Handoff

## What was built

Two repos were changed:

**posthog repo** (the main one):
- `bin/sandbox` -- added `sandbox cloud` subcommands (create, destroy, list, sleep, wake, shell, open, logs, code). These use the `aws` CLI via subprocess to manage EC2 instances. Instance state is tracked entirely via EC2 tags (no local registry).
- `bin/sandbox-entrypoint.py` -- added `SANDBOX_MODE=cloud` support: skips `.git` worktree patching and `node_modules` bind-mount (both are macOS workarounds not needed on Linux/EBS).
- `infra/cloud-sandbox/build-ami.sh` -- bash script that launches an EC2 instance, installs Docker + Tailscale, clones the repo, builds the sandbox Docker image, pulls all compose images, boots the stack to run migrations, then snapshots as an AMI.
- `infra/cloud-sandbox/cloud-init.sh` -- user data template. At boot: joins Tailscale, writes SSH keys + Claude auth, git fetches branch, starts docker compose. Placeholders like `__SANDBOX_BRANCH__` are replaced by the CLI at launch time.
- `infra/cloud-sandbox/auto-sleep.sh` -- cron script (runs every 10 min): if no SSH sessions for 2 hours, gracefully stops docker compose and shuts down the instance.
- `infra/cloud-sandbox/DECISIONS.md` -- documents all decisions and remaining placeholders.

**posthog-cloud-infra repo:**
- `terraform/modules/cloud-sandbox/` -- Terraform module: IAM role (ECR pull, SSM, optional Secrets Manager), security group (egress-only, Tailscale handles access), launch template (m6i.2xlarge, 100GB gp3, IMDSv2).
- `terraform/environments/aws-accnt-remote-dev/us-east-1/cloud-sandbox/terragrunt.hcl` -- deploys the module into the Remote Dev account (193801311984), wires up the existing VPC/subnets via the networking dependency.

## How cloud sandboxes work

1. `sandbox cloud create my-feature` launches an EC2 from a pre-built AMI in the Remote Dev account
2. Cloud-init joins Tailscale, fetches the branch, starts `docker compose -f docker-compose.sandbox.yml up`
3. The sandbox is the same self-contained compose stack that runs locally (Postgres, ClickHouse, Kafka, Redis, etc. + the app container)
4. `sandbox cloud shell my-feature` SSHs via Tailscale hostname with agent forwarding, attaches to the mprocs tmux session inside the container
5. `sandbox cloud sleep` gracefully stops compose then stops the EC2 instance (~$8/mo EBS). `sandbox cloud wake` restarts it (~1-2 min).
6. Auto-sleep cron shuts down after 2 hours with no SSH sessions.

## What the Mac agent needs to do

### Step 1: Deploy the Terraform

```bash
cd posthog-cloud-infra/terraform/environments/aws-accnt-remote-dev/us-east-1/cloud-sandbox
terragrunt apply
```

Note the outputs: `launch_template_id`, `subnet_ids`. These are needed by the CLI.

### Step 2: Build the first AMI

```bash
cd posthog/infra/cloud-sandbox
chmod +x build-ami.sh
SANDBOX_SECURITY_GROUP=<sg-id> SANDBOX_SUBNET_ID=<subnet-id> ./build-ami.sh
```

This takes ~15-20 min. **No SSH required** -- all provisioning happens via cloud-init user data on the instance. The script:
- Finds the latest Ubuntu 24.04 AMI
- Launches an instance with a user-data script that does all the setup
- Polls an EC2 tag (`build-status`) until the instance reports `complete`
- Stops the instance and snapshots as AMI
- Outputs the AMI ID

The build script needs these env vars (or will use defaults):
- `AWS_REGION` (default: us-east-1)
- `SANDBOX_SECURITY_GROUP` -- from Terraform output
- `SANDBOX_SUBNET_ID` -- from Terraform output (pick one private subnet)
- `SANDBOX_INSTANCE_PROFILE` -- (default: cloud-sandbox)
- `AWS_KEY_NAME` -- optional, for SSH debug access if needed

If the build fails, you can debug via SSM Session Manager:
```bash
aws ssm start-session --target <instance-id>
cat /var/log/sandbox-ami-build.log
```

### Step 3: Update Terraform with the AMI

Edit `posthog-cloud-infra/terraform/environments/aws-accnt-remote-dev/us-east-1/cloud-sandbox/terragrunt.hcl`, set `ami_id` to the AMI ID from step 2, then `terragrunt apply` again.

### Step 4: Test it

```bash
cd posthog
bin/sandbox cloud create test-branch
```

On first run, it prompts for:
- Launch template ID (from Terraform output)
- Subnet ID (pick one private subnet)
- AWS region (us-east-1)
- AWS CLI profile name
- Tailscale auth key (generate a reusable key from the Tailscale admin console -- personal account is fine for testing)

These are saved to `~/.posthog-sandboxes/cloud-config.json`.

Then:
```bash
bin/sandbox cloud list              # verify it shows up
bin/sandbox cloud shell test-branch # SSH in
bin/sandbox cloud sleep test-branch # stop instance
bin/sandbox cloud wake test-branch  # restart
bin/sandbox cloud destroy test-branch # clean up
```

## Key things to watch for

1. **Tailscale reconnection after stop/start** -- reusable auth keys handle this, but verify the hostname persists.
2. **The `SANDBOX_MODE=cloud` env var** -- must be set in cloud-init so the entrypoint skips macOS-specific workarounds. It's already in the cloud-init.sh template.
