## Problem

Teams using event schema validation need a middle ground between "allow" (no enforcement) and "reject" (hard block). They also need a way to know when cached validation results are stale after schema changes, and a kill switch to disable validation entirely during incidents.

## Changes

- New `enforce` enforcement mode on `EventDefinition`, between "allow" and "reject"
- `schema_version` on `EventDefinition`, auto-incremented when schemas change
- `validated_schema_version` column in ClickHouse events tables
- `schema_validation_disabled` kill switch on `Team`
- Django and ClickHouse migrations, updated query snapshots

## How did you test this code?

I am an agent and have not manually tested this code. The branch includes updated query snapshots across multiple test suites to reflect the new `schema_validation_disabled` team field and `validated_schema_version` events column.

👉 _Stay up-to-date with [PostHog coding conventions](https://posthog.com/docs/contribute/coding-conventions) for a smoother review._

## Publish to changelog?

no

## Docs update

<!-- Add the `skip-inkeep-docs` label if this PR should not trigger an automatic docs update from the Inkeep agent. -->

## 🤖 LLM context

This PR description was authored by an LLM agent based on code review of the branch diff.
