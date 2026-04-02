# Cloud Sandbox - Decisions & Placeholders

Things that need human input before this is fully operational.
Code uses placeholder values for all of these so development can continue.

## AWS

Terraform lives in `posthog-cloud-infra/terraform/modules/cloud-sandbox/` and is
deployed to the Remote Dev account (193801311984) via terragrunt at
`environments/aws-accnt-remote-dev/us-east-1/cloud-sandbox/`.

The VPC and private subnets already exist in that account (10.70.0.0/16).

- [x] **AWS Account**: Remote Dev (193801311984)
- [x] **Region**: us-east-1
- [x] **VPC / Subnets**: Existing networking in remote-dev account
- [ ] **AWS CLI profile name**: What profile name should engineers use to access the remote-dev account?

## Tailscale

Generic setup -- provide any Tailscale auth key at sandbox creation time.
For testing, use a personal Tailscale account. For production, create an
org-level reusable auth key tagged `tag:sandbox`.

- [ ] **Auth key**: Provide at sandbox creation time (stored in ~/.posthog-sandboxes/cloud-config.json)
- [ ] **ACL changes** (later): Add `tag:sandbox`, allow `group:engineering` on ports 8000, 8234, 2222

## Instance sizing

- [x] **Instance type**: m6i.2xlarge (8 vCPU, 32GB, x86)
- [x] **Root EBS size**: 100GB gp3

## Claude Code auth

- [x] **Method**: Passed in user data. Acceptable for v0 (private subnet, Tailscale-only access).

## Git auth

- [x] **v0**: SSH agent forwarding. PostHog repo is public, so git fetch at boot works over HTTPS.

## AMI

- [x] **Build cadence**: Manual for Phase 1 (build-ami.sh)
- [x] **Retention**: Keep last 3 AMIs (handled by build-ami.sh)
- [x] **Base AMI**: Auto-discovered Ubuntu 24.04 x86_64

## To deploy

1. Get AWS CLI access to the remote-dev account
2. `cd posthog-cloud-infra/terraform/environments/aws-accnt-remote-dev/us-east-1/cloud-sandbox`
3. `terragrunt apply`
4. Note the `launch_template_id` and `subnet_ids` from the output
5. Run `build-ami.sh` from the posthog repo to create the first AMI
6. Update `ami_id` in terragrunt.hcl and re-apply
7. Run `sandbox cloud create <branch>` -- it will prompt for config on first use
