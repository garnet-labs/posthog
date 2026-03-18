---
name: hogli
description: >
  PostHog developer CLI and repo tooling reference. Use when the user mentions
  hogli, asks about repo CLI tools, bin scripts, Makefiles, how to run/build/test/lint,
  or any dev environment commands.
---

# hogli - PostHog Developer CLI

Unified CLI for PostHog development. Wraps all repo scripts, bin commands, and tooling behind a single entry point. There is no Makefile — hogli is the equivalent.

Run `hogli --help` to get the full, current command list. Run `hogli <command> --help` for any subcommand.

## Process logging (for agents/debugging)

`hogli dev:setup --log` enables file logging for all mprocs processes. Logs go to `/tmp/posthog-<process>.log` where `<process>` matches the mprocs process key (see `bin/mprocs.yaml`).

## Key references

- `common/hogli/manifest.yaml` — command definitions (source of truth)
- `common/hogli/commands.py` — extension point for custom Click commands
- `common/hogli/README.md` — full developer and architecture docs
- `.agents/skills/isolating-product-facade-contracts/SKILL.md` — AI-assisted product isolation migrations to facade + contracts architecture

## Product commands

- `hogli product:bootstrap <name>` — scaffold a new product with canonical structure. Supports `--dry-run` and `--force`.
- `hogli product:lint <name>` — validate a single product's structure. Runs in **strict** mode (all rules enforced) for isolated products with `backend/facade/contracts.py`, or **lenient** mode (subset of rules) for legacy products. Single-product runs show detailed, actionable hints per check.
- `hogli product:lint --all` — lint every product. Compact pass/fail output per product.
