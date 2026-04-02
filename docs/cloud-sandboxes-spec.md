# Cloud Sandboxes

**Status:** In progress (Phase 1 built, pending deploy + test)
**Author:** Alexander Spicer
**Date:** 2026-04-01

## What

Each cloud sandbox is an EC2 instance running `docker compose up` on the existing `docker-compose.sandbox.yml`.
Same system as a local sandbox, just on a remote machine.
Protected by Tailscale. Accessible via SSH, VS Code Remote-SSH, JetBrains Gateway, or browser.

**Killer use case:** Run Claude Code on a cloud sandbox so it doesn't eat your laptop while you're in meetings. Kick off a task, close your laptop, come back to a completed PR.

**Editing workflow:** You edit code on the sandbox, not locally. Connect via VS Code Remote-SSH, JetBrains Gateway, or SSH + your editor. The sandbox is your dev machine. Your laptop is a thin client.

## Architecture

```
Developer laptop                         AWS Remote Dev account (private subnet)
  sandbox cloud create my-feature  --->  EC2 instance (m6i.2xlarge, 8 vCPU, 32GB)
  sandbox cloud shell my-feature   --->    docker compose up (unchanged compose file)
  VS Code Remote-SSH               --->    Tailscale (employee-only access)
  http://sandbox-alice-my-feature  --->    PostHog running on :8000
```

- **No server.** The CLI calls `aws` CLI directly. Sandbox state = EC2 instance tags.
- **No rearchitecting.** Same `Dockerfile.sandbox`, `docker-compose.sandbox.yml`, and `bin/sandbox-entrypoint.py`. ~10 lines of entrypoint changes for cloud mode.
- **Pre-built AMI** with repo, Docker images, deps, and migrated databases baked in. Boot under 5 minutes.
- **Sleep = `ec2:StopInstances`** (EBS persists, $8/mo). **Wake = `ec2:StartInstances`** (~1-2 min).
- **Auto-sleep** after 2 hours idle. **Auto-destroy** after 14 days sleeping (Phase 3).

## CLI

`sandbox cloud` is a subcommand of the existing `bin/sandbox`.

```bash
sandbox cloud create <branch>     # Launch a sandbox, boot under 5 min
sandbox cloud shell <branch>      # SSH in (lands in tmux with mprocs)
sandbox cloud code <branch>       # Open VS Code Remote-SSH
sandbox cloud open <branch>       # Open PostHog web UI in browser
sandbox cloud sleep <branch>      # Graceful stop, keep disk ($8/mo)
sandbox cloud wake <branch>       # Restart (~1-2 min)
sandbox cloud destroy <branch>    # Terminate, delete everything
sandbox cloud list                # Show your sandboxes
sandbox cloud logs <branch>       # Tail boot and app logs
```

## Git auth

**v0: SSH agent forwarding.** When you SSH in, your local SSH key is available. Private key never leaves your laptop. Works with VS Code Remote-SSH and JetBrains Gateway.

```bash
sandbox cloud shell my-feature
git push origin my-feature  # Uses your SSH key via forwarded agent
```

The main workflow (Claude Code reading code, iterating, running tests) all works without the forwarded agent -- you'd just need to reconnect to push. If autonomous git push becomes a real need, a v2 could use a GitHub App token scoped to the repo. See [Appendix C](#appendix-c-git-auth-options) for the full options analysis.

## Phases

### Phase 1: Working prototype (3-5 days) -- BUILT

**What you get:** `sandbox cloud create my-feature`, SSH in, PostHog works. Boot under 5 min.

- [x] AMI build script (`infra/cloud-sandbox/build-ami.sh`): launches instance with cloud-init user data that installs Docker + Tailscale, clones repo, pulls images, runs migrations. Polls EC2 tag for completion, then snapshots. No SSH needed.
- [x] Cloud-init user data template (`infra/cloud-sandbox/cloud-init.sh`): Tailscale up, git fetch branch, write SSH keys + Claude auth, `docker compose up`
- [x] Terraform module (`posthog-cloud-infra/terraform/modules/cloud-sandbox/`): launch template, security group, IAM role. Deployed via terragrunt to the Remote Dev account (193801311984).
- [ ] Tailscale: generic setup -- provide any auth key at sandbox creation. Org-level ACLs deferred.
- [x] Entrypoint changes for `SANDBOX_MODE=cloud` (`bin/sandbox-entrypoint.py`)
- [x] Auto-sleep cron (`infra/cloud-sandbox/auto-sleep.sh`): if no SSH sessions for 2 hours, graceful docker compose stop + shutdown
- [x] Full CLI commands in `bin/sandbox` (create, destroy, list, sleep, wake, shell, open, logs, code) with graceful shutdown on sleep

**Remaining:** Deploy Terraform, build first AMI, test end-to-end.

### Phase 2: Self-serve (1 week)

**What you get:** Any engineer can use cloud sandboxes without help.

- [ ] Nightly AMI build in CI (GitHub Actions)
- [ ] Documentation and onboarding guide
- [ ] Tailscale org-level ACLs (`tag:sandbox`, `group:engineering`)

### Phase 3: Don't go broke (3-5 days)

**What you get:** Forgotten sandboxes don't accumulate cost.

- [ ] Auto-sleep: Lambda checks CPU, sleeps idle instances after 1 hour
- [ ] Auto-destroy: Lambda destroys sandboxes sleeping 14+ days
- [ ] Slack notifications for sleep/destroy
- [ ] Cost tags on instances
- [ ] VPC endpoints for ECR and S3 (reduce NAT Gateway costs)

### Phase 4: Polish (ongoing)

- [ ] Wake-on-access (proxy wakes sleeping sandboxes on first request)
- [ ] GitHub PR integration (`/cloud-sandbox` comment)
- [ ] Spot instances
- [ ] GitHub App token for autonomous Claude Code git push (if needed)

**Total phases 1-3: ~2-3 weeks.** Realistically budget 4 weeks for one engineer including infra iteration time.

## Cost

| State | Monthly cost per sandbox |
|---|---|
| Active (m6i.2xlarge, on-demand) | **~$280** |
| Sleeping (EBS only) | **~$8** |

| Scenario | Active | Sleeping | Monthly |
|---|---|---|---|
| Early (20 engineers) | 20 | 20 | **~$5,800** |
| Medium (50 engineers) | 50 | 200 | **~$15,600** |
| Full (150 engineers) | 150 | 500 | **~$46,000** |

2hr auto-sleep + 14-day auto-destroy keeps the sleeping pool small. Fixed costs: ~$100-500/mo (mostly NAT Gateway).

---

## Appendix A: Infrastructure Details

### Instance configuration

- **Instance type:** `m6i.2xlarge` (8 vCPU, 32GB RAM, Intel x86_64)
- **Root EBS:** 100GB gp3 (OS + Docker images + repo + all Docker volumes on one disk)
- **Private subnet**, no public IP (access exclusively via Tailscale)
- **IAM profile:** ECR pull, SSM Session Manager, self-tagging (for AMI builds)
- **Tags:** `sandbox=true`, `sandbox:owner=<user>`, `sandbox:branch=<branch>`, `sandbox:hostname=<tailscale-hostname>`, `sandbox:created=<date>`

### Terraform

Terraform lives in the `posthog-cloud-infra` repo:
- **Module:** `terraform/modules/cloud-sandbox/` (IAM role, security group, launch template)
- **Environment:** `terraform/environments/aws-accnt-remote-dev/us-east-1/cloud-sandbox/`
- **AWS Account:** Remote Dev (193801311984), VPC 10.70.0.0/16, existing private subnets

### AMI build

Built by `infra/cloud-sandbox/build-ami.sh`. No SSH required -- all provisioning happens via cloud-init user data. The script launches an instance, polls an EC2 tag (`build-status`) until complete, then snapshots. Manual for Phase 1, nightly CI in Phase 2. Keep last 3 good AMIs.

**AMI contains:** Ubuntu 24.04 x86_64, Docker, Tailscale, repo at master HEAD, all Docker images pre-pulled, sandbox Docker image pre-built, Postgres + ClickHouse pre-migrated, auto-sleep cron installed.

**At boot (on top of AMI):** Tailscale up, git fetch + checkout branch, write SSH keys + Claude auth, `docker compose up`, incremental deps + migrations.

**Debugging AMI builds:** If the build fails, use SSM Session Manager:
```bash
aws ssm start-session --target <instance-id>
cat /var/log/sandbox-ami-build.log
```

### Tailscale

- Reusable auth keys (reconnects after EC2 stop/start)
- Hostname: `sandbox-{user}-{branch-slug}` (truncate at 56 chars + hash if over 63)
- Generic for Phase 1 (personal Tailscale account for testing). Org-level ACLs in Phase 2.
- CLI removes Tailscale node on destroy

### Sleep / wake mechanics

- **Sleep:** CLI runs `docker compose stop` via SSH (graceful -- ClickHouse and Kafka don't like hard kills), then `ec2:StopInstances`. EBS persists.
- **Wake:** `ec2:StartInstances`. Docker restarts. Tailscale reconnects. ~1-2 minutes.
- **Auto-sleep:** Cron on the instance (every 10 min) shuts down after 2 hours of no SSH sessions.
- **Phase 3 auto-sleep:** Lambda checks CloudWatch CPU < 10% for 1 hour, then graceful stop.
- **Auto-destroy (Phase 3):** Lambda destroys sandboxes sleeping 14+ days. Slack notification first.

### Entrypoint changes

Set `SANDBOX_MODE=cloud` in cloud-init. ~10 lines changed in `bin/sandbox-entrypoint.py`:

| Behavior | Local | Cloud |
|---|---|---|
| `.git` worktree patching | Patches `.git` to `/repo.git` | **Skip** -- normal git dir |
| `mount --bind` for node_modules | VirtioFS workaround | **Skip** -- EBS is fast |
| `SYS_ADMIN` capability | Required | **Not needed** |
| Git fetch on wake | Not needed | **Add:** `git fetch && git checkout <branch>` |

---

## Appendix B: Risks

### Check before building

| What | Why | How |
|---|---|---|
| Tailscale plan limits | Could be 500+ devices at scale | Ask Tailscale |

### Watch during build

| What | Why |
|---|---|
| Cloud-init debugging | Iteration is slow: launch, wait, check tags, read logs via SSM, fix, re-launch. Budget extra time. |
| File permissions | Repo cloned as root on host, container runs as sandbox user. May need `chown`. |
| NAT Gateway costs | Docker pulls + package installs go through NAT. VPC endpoints help (Phase 3). |

### Non-risks (investigated, fine)

- **VPC capacity:** Remote Dev VPC is a /16 (65K IPs). Plenty of room.
- **Docker Compose restart after stop/start:** We do `docker compose stop` (graceful) before stopping the instance. Services come back clean.
- **Tailscale reconnection after stop/start:** Reusable auth keys persist state on disk. Reconnects automatically. Same pattern as existing Tailscale subnet routers.
- **32GB RAM:** The local sandbox runs the same stack on a laptop. 32GB is plenty.
- **AMI staleness:** Docker images are pinned in the compose file. At boot, git fetches the branch, entrypoint runs incremental `uv sync`/`pnpm install`. Only the branch delta is pulled. 24-hour-old AMI is fine.

---

## Appendix C: Git Auth Options

For v0, we use Option A. Options B and C are documented here for future reference if autonomous git push becomes a real need.

### Option A: SSH agent forwarding (v0)

Your local SSH key is forwarded when you connect. Git operations use your key without it leaving your laptop.

| Pro | Con |
|---|---|
| Zero setup | Only works while connected |
| Key never leaves laptop | Claude Code can't push autonomously |
| No tokens to manage | |

Note: Claude Code can still read, write, run tests, and iterate fully autonomously. Only `git push` requires a connected session.

### Option B: GitHub App token (future, if needed)

Create a GitHub App (`posthog-sandbox-bot`) with `contents: write`, `pull_requests: write`, `metadata: read`. Explicitly NO `workflows` permission (can't edit CI files).

CLI generates a short-lived token at sandbox creation, written to a file on the instance. Cron refreshes it every 50 minutes.

| Pro | Con |
|---|---|
| Works without anyone connected | Tokens expire hourly, need refresh cron |
| Scoped permissions (no CI modification) | One more thing to maintain |
| Developer is the commit author, not the bot | |

**CI triggering:** App tokens DO trigger CI. Mitigate by configuring workflows to trigger on `push: branches: [master]` + `pull_request` only.

### Option C: Deploy key per sandbox (not recommended)

Unique SSH deploy key per sandbox, added/removed via GitHub API.

| Pro | Con |
|---|---|
| Works without anyone connected | Managing hundreds of deploy keys |
| No expiry | Per-repo only, can't push to forks |

Not worth the management overhead.

---

## Appendix D: Why Not Codespaces?

The repo has a Codespaces/devcontainer setup but it's unmaintained and doesn't work. Codespaces can't run the full PostHog stack (ClickHouse, Kafka, etc.) reliably on available machine types.

## Appendix E: Security

- **No public IPs.** Private subnets only. Access exclusively via Tailscale.
- **No credentials stored on sandboxes.** Git auth uses SSH agent forwarding. Claude Code auth is passed via user data (acceptable for private subnet + Tailscale-only access).
- **Full VM isolation.** Each sandbox is its own EC2 instance. No shared kernel.
- **SSM Session Manager** as fallback access for debugging.
- **EBS encryption at rest.**
- **IMDSv2 enforced** (no v1 metadata access).
