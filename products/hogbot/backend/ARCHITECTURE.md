# Hogbot architecture

## Purpose

This document describes the **current architecture** for hogbot sandbox session orchestration.

It is intended for engineers joining the project who need a durable, high-level explanation of how hogbot works today, what building blocks already exist, and how the system is meant to evolve. It captures the **state of the implementation so far**, rather than the original step-by-step implementation plan.

## Design goals

The current design is built around a small set of explicit goals:

- **One active hogbot session per team**
  - A team should have at most one active sandbox-backed hogbot session at a time.
- **One-shot Temporal workflow per active session**
  - Hogbot does not use a permanently running Temporal workflow.
  - Instead, each active session is represented by a single workflow execution with a clear start and end.
- **Persist filesystem state across sessions**
  - Sandbox filesystem state should survive across sessions by creating snapshots at the end of successful runs and restoring from the latest snapshot on the next run.
- **Keep Temporal history small**
  - Temporal should orchestrate lifecycle, not every application-level interaction.
  - Only lightweight lifecycle signals flow through the workflow.
- **Allow direct communication with the sandbox HTTP server**
  - External systems should be able to talk directly to the hogbot HTTP server running in the sandbox instead of proxying all traffic through Temporal.

## Core building blocks

The current implementation is composed of a few primary pieces:

- **`HogbotRuntime` model**
  - Located in `products.hogbot.backend.models`
  - Stores durable per-team runtime state and links one workflow execution to the next.
- **Gateway helpers**
  - Located in `products.hogbot.backend.gateway`
  - Provide the main control entrypoints for starting a session and sending lifecycle signals.
- **Temporal workflow**
  - Located in `products.hogbot.backend.temporal.workflow`
  - Owns the lifecycle of a single hogbot session.
- **Temporal activities**
  - Located in `products.hogbot.backend.temporal.activities`
  - Encapsulate the concrete side effects: sandbox creation, server start, snapshotting, runtime state updates, log reading, and cleanup.
- **Shared sandbox abstraction**
  - Located in `products.tasks.backend.services.sandbox`
  - Provides the provider-agnostic interface for creating and operating sandboxes.

## Sandbox layer

Hogbot reuses the existing sandbox abstraction already used by the tasks system. This is an intentional design choice: hogbot should not invent a second sandbox orchestration stack when the repository already has a shared, provider-neutral layer for sandbox lifecycle management.

The sandbox abstraction supports multiple backends:

- **Modal** is the default production backend
- **Docker** is the local and development backend

Sandbox creation supports restoring filesystem state using a previously stored `snapshot_external_id`. In practice, this means a new hogbot session can start from the latest persisted filesystem image instead of always booting from a clean base environment.

The sandbox layer also exposes **connect credentials** and an externally reachable URL where appropriate. The workflow uses this to surface connection information for the HTTP server that runs inside the sandbox.

Health check behavior currently depends on the backend:

- **Modal:** port `8080`
- **Docker:** port `47821`

These provider-specific ports are part of the current server start contract.

## Temporal session lifecycle

The current workflow is named:

- **`hogbot-session`**

Each session is keyed by the workflow id:

- **`hogbot-team-{team_id}`**

This gives hogbot a stable team-scoped identity while still allowing a new one-shot workflow execution for each completed session.

### Current lifecycle

A hogbot session currently flows through these steps:

1. **Load latest snapshot id from runtime state before start**
   - The gateway reads the current `HogbotRuntime` row for the team and passes the latest snapshot id into workflow input.
2. **Create sandbox from snapshot or fresh base image**
   - The workflow calls the sandbox creation activity, which restores from snapshot when possible and otherwise creates a fresh sandbox.
3. **Start HTTP server inside sandbox**
   - The workflow starts the hogbot server process inside the sandbox and waits for its health check to pass.
4. **Persist runtime state as running**
   - Runtime state is updated with sandbox identity, server URL, workflow metadata, and the `running` status.
5. **Wait on `heartbeat()` and `complete(...)`**
   - The workflow then idles in a lifecycle loop.
   - Heartbeats reset the inactivity timer.
   - Completion ends the session.
6. **On successful completion create snapshot**
   - If the workflow is completed with a success status, it creates a new filesystem snapshot.
7. **Persist new snapshot id to runtime model**
   - The latest snapshot id is written into `HogbotRuntime` so the next run can resume from it.
8. **Always read logs and cleanup sandbox**
   - Whether the run succeeds or fails, the workflow reads sandbox logs and destroys the sandbox.
9. **Mark final runtime status**
   - The runtime row is updated with the final session state and any final error context.

This lifecycle keeps Temporal responsible for orchestration while leaving ongoing application traffic outside the workflow.

## Activities

The workflow is intentionally small because most concrete work lives in activities.

### `create_hogbot_sandbox`

Responsibility:

- Create a sandbox for a team using the shared sandbox abstraction
- Restore from `snapshot_external_id` when available
- Return:
  - sandbox id
  - externally reachable sandbox URL
  - connect token when the backend requires one

Architecturally, this is the entrypoint into the sandbox layer. It translates high-level session intent into a concrete sandbox instance.

### `start_hogbot_server`

Responsibility:

- Start the hogbot HTTP server inside the sandbox as a background process
- Write server logs to `/tmp/hogbot-server.log`
- Wait for the sandbox-local health endpoint to become ready
- Return the externally reachable server URL and any connect token

This activity is the boundary between “sandbox exists” and “usable hogbot server is live.” It is also where provider-specific health check port assumptions are currently enforced.

### `update_hogbot_runtime_state`

Responsibility:

- Create or load the `HogbotRuntime` row for a team
- Persist status and any supplied runtime metadata

This activity exists so the workflow can update durable runtime state without embedding ORM logic directly into workflow code. It is the persistence bridge between Temporal orchestration and database state.

### `create_resume_snapshot`

Responsibility:

- Create a filesystem snapshot from the running sandbox
- Return the resulting external snapshot id or an error

This activity is intentionally narrow. It no longer persists anything task-specific and does not depend on task models. Its only job is to convert a live sandbox into a resumable snapshot artifact.

### `read_sandbox_logs`

Responsibility:

- Read the hogbot server log file from the sandbox before destruction
- Return the captured log text

This gives the workflow a last chance to retrieve server-side context before cleanup. It is primarily useful for debugging, postmortem visibility, and eventually operator tooling.

### `cleanup_sandbox`

Responsibility:

- Best-effort destruction of the sandbox

This activity is deliberately simple and defensive. Cleanup should always happen, but failure to destroy the sandbox should not prevent the workflow from finishing its own finalization logic.

### `track_workflow_event`

Responsibility:

- Emit workflow-level analytics events

This is currently a lightweight helper for recording lifecycle events. It is not central to the orchestration design, but it provides a hook for observability without pushing those concerns directly into the workflow core.

## Runtime state model

The `HogbotRuntime` model exists to store durable, per-team session state across one-shot workflow executions.

Today it stores fields such as:

- latest snapshot external id
- active workflow id
- active run id
- sandbox id
- server URL
- status
- last error

Its architectural role is important: it is the **bridge between one-shot workflow executions**.

A session workflow eventually ends. The runtime row is what lets the next session know:

- which snapshot to restore from
- what the most recent state was
- what workflow currently owns the team session
- whether there is any recent failure context to inspect

Without this model, each session would be isolated and the system would lose the continuity required for resumable sandbox state.

## Signaling model

The workflow receives only **lightweight lifecycle signals**.

### `heartbeat()`

- Signals that the session is still alive and in use
- Resets the inactivity timeout window
- Prevents the workflow from timing out while the external system is still using the sandbox server

### `complete(...)`

- Ends the session
- Carries the final completion status
- Determines whether the success path, including snapshot creation, should run

This signaling model is intentionally narrow. The workflow is **not** the message bus for all hogbot interaction or chat traffic. That traffic is expected to flow directly to the HTTP server inside the sandbox.

This keeps Temporal focused on what it is best at:

- lifecycle orchestration
- durability
- retries
- cleanup
- finalization

It avoids turning Temporal into a transport for high-volume or conversational application traffic.

## Gateway and control flow

The current gateway layer exposes the main synchronous control helpers:

- `start_or_restart_hogbot`
- `heartbeat_hogbot`
- `complete_hogbot`

### `start_or_restart_hogbot`

This helper:

- loads or creates the `HogbotRuntime` row
- reads the latest snapshot id from the runtime row
- starts the `hogbot-session` workflow
- refreshes runtime state from the database before returning it

The workflow itself is treated as authoritative for workflow/run metadata persistence once it starts.

### `heartbeat_hogbot`

This helper:

- resolves the workflow handle from `hogbot_workflow_id(team_id)`
- signals the workflow heartbeat method

### `complete_hogbot`

This helper:

- resolves the workflow handle from `hogbot_workflow_id(team_id)`
- signals workflow completion with status and optional error message

### Start semantics

Session start currently uses Temporal workflow start behavior that supports:

- **one workflow id per team**
- reuse of that workflow id across completed runs
- coexistence of team-scoped identity with one-shot execution semantics

That combination is what allows the design to be both team-scoped and session-oriented.

## Worker registration and discoverability

The hogbot Temporal package is registered in:

- `products.hogbot.backend.temporal.__init__`

This is the package-level source of truth for the workflow and activities exposed by hogbot.

It is also wired into:

- `posthog/management/commands/start_temporal_worker.py`
- `posthog/management/commands/start_temporal_workflow.py`
- `posthog/management/commands/execute_temporal_workflow.py`

This means:

- the workflow is runnable by the Temporal worker
- the workflow is discoverable from the existing management commands
- hogbot currently uses the existing tasks-oriented Temporal queue infrastructure rather than a dedicated queue

## Current limitations and rough edges

The current implementation is intentionally minimal and has a few known rough edges:

- **Server start assumes a health endpoint exists**
  - The start activity assumes the process exposes a health endpoint on the expected port.
- **Gateway returns runtime state from the database**
  - It does not yet query live workflow state or live connection info directly from Temporal queries.
- **Snapshotting currently runs only on `complete(status="completed")`**
  - Other completion statuses do not take the snapshot success path.
- **Transient runtime fields are cleared with empty strings rather than nulls**
  - This works, but the clearing semantics are not yet ideal.
- **API and presentation layers are not yet built around these helpers**
  - The architecture exists, but a full external control surface is still missing.

## Next likely steps

The most likely next steps in this architecture are:

- **Expose API endpoints or service methods**
  - Add supported entrypoints for session start, heartbeat, completion, and status.
- **Tighten runtime clearing semantics**
  - Move transient runtime fields to cleaner null-based clearing behavior.
- **Make health checks more configurable**
  - Allow health path and maybe health port assumptions to be configured more explicitly.
- **Enrich tests**
  - Expand workflow coverage around success, timeout, failure, and signaling behavior.

## Summary

The current hogbot architecture is a team-scoped, snapshot-backed sandbox session system built around a one-shot Temporal workflow.

Temporal is responsible for:

- starting a session
- keeping it alive through heartbeats
- completing it
- snapshotting it
- cleaning it up

The sandbox HTTP server is responsible for the direct runtime interaction surface.

`HogbotRuntime` provides the durable continuity between otherwise separate workflow executions, and the shared sandbox abstraction provides the provider-neutral execution environment that hogbot builds on today.
