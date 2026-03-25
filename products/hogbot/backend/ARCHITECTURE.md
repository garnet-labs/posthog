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
  - Only lightweight lifecycle operations flow through the workflow.
- **Allow direct communication with the sandbox HTTP server**
  - External systems should be able to talk directly to the hogbot HTTP server running in the sandbox instead of proxying all traffic through Temporal.

## Core building blocks

The current implementation is composed of a few primary pieces:

- **`HogbotRuntime` model**
  - Located in `products.hogbot.backend.models`
  - Minimal per-team persistence: stores only the latest snapshot external ID for session continuity.
- **Gateway helpers**
  - Located in `products.hogbot.backend.gateway`
  - Provide the main control entrypoint for starting a session and waiting for it to become ready.
- **Temporal workflow**
  - Located in `products.hogbot.backend.temporal.workflow`
  - Owns the lifecycle of a single hogbot session.
- **Temporal activities**
  - Located in `products.hogbot.backend.temporal.activities`
  - Encapsulate the concrete side effects: sandbox creation, server start, server exit waiting, snapshotting, log reading, and cleanup.
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

- **`hogbot`**

Each session is keyed by the workflow id:

- **`hogbot-team-{team_id}`**

This gives hogbot a stable team-scoped identity while still allowing a new one-shot workflow execution for each completed session.

### Current lifecycle

A hogbot session currently flows through these phases:

1. **`pending`** — workflow initialized, nothing started yet
2. **`starting`** — sandbox creation and server start in progress
   - The workflow calls `create_hogbot_sandbox` to provision the sandbox (restoring from snapshot when available)
   - Then calls `start_hogbot_server` to start the HTTP server and wait for its health check
3. **`running`** — server is live and accepting traffic
   - The workflow marks `ready=True` and enters a long-running `wait_for_hogbot_server_exit` activity (up to 8 days, with 1-minute heartbeat timeout)
   - External systems talk directly to the sandbox server URL
4. **`snapshotting`** — server has exited cleanly, creating a filesystem snapshot
   - Only runs if the server exited with `completed` status
   - Creates a snapshot via `create_resume_snapshot` and persists the snapshot ID via `persist_hogbot_snapshot`
5. **`cleaning_up`** — reading logs and destroying the sandbox
   - Always runs in the `finally` block regardless of success or failure
   - Reads server logs via `read_sandbox_logs`, then destroys the sandbox via `cleanup_sandbox`
6. **`completed`** or **`failed`** — final terminal state

This lifecycle keeps Temporal responsible for orchestration while leaving ongoing application traffic outside the workflow.

## Activities

The workflow is intentionally small because most concrete work lives in activities.

### `create_hogbot_sandbox`

Responsibility:

- Create a sandbox for a team using the shared sandbox abstraction
- Optionally clone a repository and check out a branch (via GitHub integration)
- Restore from snapshot when available
- Return sandbox ID, externally reachable URL, and connect token

This is the entrypoint into the sandbox layer. It translates high-level session intent into a concrete sandbox instance.

### `start_hogbot_server`

Responsibility:

- Start the hogbot HTTP server inside the sandbox as a background process
- Write server logs to `/tmp/hogbot-server.log`
- Wait for the sandbox-local health endpoint to become ready
- Return the externally reachable server URL and any connect token

This activity is the boundary between "sandbox exists" and "usable hogbot server is live." It is also where provider-specific health check port assumptions are currently enforced.

### `wait_for_hogbot_server_exit`

Responsibility:

- Monitor the sandbox process until the hogbot server exits
- Run as a long-lived activity (up to 8 days) with a 1-minute heartbeat timeout
- Return the exit status, exit code, and any error message

This is the main "idle" phase of the workflow. While this activity is running, the sandbox server is live and accepting direct HTTP traffic. The activity simply waits for the server process to terminate.

### `create_resume_snapshot`

Responsibility:

- Create a filesystem snapshot from the running sandbox
- Return the resulting external snapshot ID or an error

This activity is intentionally narrow. It does not persist anything — its only job is to convert a live sandbox into a resumable snapshot artifact.

### `persist_hogbot_snapshot`

Responsibility:

- Write the snapshot external ID to the `HogbotRuntime` model for the team

This is the persistence bridge that links one workflow execution to the next. The next session can read the latest snapshot ID from the runtime model and restore from it.

### `read_sandbox_logs`

Responsibility:

- Read the hogbot server log file from the sandbox before destruction
- Return the captured log text

This gives the workflow a last chance to retrieve server-side context before cleanup. Logs are recorded to the Temporal workflow logger for observability.

### `cleanup_sandbox`

Responsibility:

- Best-effort destruction of the sandbox

This activity is deliberately simple and defensive. Cleanup should always happen, but failure to destroy the sandbox should not prevent the workflow from finishing its own finalization logic.

### `track_workflow_event`

Responsibility:

- Emit workflow-level analytics events

This is a lightweight helper for recording lifecycle events. It provides a hook for observability without pushing those concerns directly into the workflow core.

## Runtime state model

The `HogbotRuntime` model is minimal. It stores only:

- `team` (OneToOne primary key to Team)
- `latest_snapshot_external_id` — the snapshot to restore from on the next session
- `created_at` / `updated_at` timestamps

All transient session state (workflow ID, run ID, sandbox ID, server URL, connect token, phase, readiness, errors) lives in the **workflow itself** and is accessed via Temporal queries. This keeps the database model thin and avoids stale state problems from dual-writing.

## Workflow queries

The workflow exposes two Temporal queries for inspecting live session state:

### `get_connection_info`

Returns a dict with: `workflow_id`, `run_id`, `phase`, `ready`, `sandbox_id`, `server_url`, `connect_token`, `error`.

This is the primary query used by the gateway to poll for readiness after starting a workflow.

### `get_status`

Returns the same fields as `get_connection_info` — an alias for convenience.

## Gateway and control flow

The current gateway layer exposes the main synchronous control helper:

### `get_or_start_hogbot`

This is the primary entrypoint for obtaining a running hogbot session. It:

1. Starts the `hogbot` workflow (or attaches to an existing one via `USE_EXISTING` conflict policy)
2. Polls the workflow's `get_connection_info` query until `ready=True` or a terminal phase is reached
3. If the workflow is in a closing phase, waits for it to finish and retries (up to 3 attempts)
4. Returns a `HogbotConnectionInfo` dataclass with the sandbox URL, connect token, and readiness state

The polling uses a 0.5-second interval with a 120-second timeout.

### `start_or_restart_hogbot`

An alias for `get_or_start_hogbot` — provided for semantic clarity at call sites.

### Start semantics

Session start uses Temporal's `WorkflowIDConflictPolicy.USE_EXISTING` combined with `WorkflowIDReusePolicy.ALLOW_DUPLICATE`. This means:

- If a workflow is already running for the team, the gateway attaches to it
- If no workflow exists (or the previous one completed), a new one is started
- The same workflow ID is reused across sessions

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

The current implementation has a few known rough edges:

- **Server start assumes a health endpoint exists**
  - The start activity assumes the process exposes a health endpoint on the expected port.
- **No signal-based interaction**
  - The workflow does not currently accept heartbeat or completion signals. Session lifetime is determined by the server process exit.
- **Snapshotting only runs on clean server exit**
  - If the server exits with a non-completed status, no snapshot is created.
- **API and presentation layers are partially built**
  - The hogbot viewset exists with stub endpoints for logs, send-message, and file access, but is not yet wired to the gateway or live sandbox.

## Summary

The current hogbot architecture is a team-scoped, snapshot-backed sandbox session system built around a one-shot Temporal workflow.

Temporal is responsible for:

- provisioning the sandbox (optionally from a snapshot)
- starting the HTTP server
- waiting for the server to exit
- snapshotting on success
- cleaning up the sandbox

The sandbox HTTP server is responsible for the direct runtime interaction surface.

`HogbotRuntime` provides minimal cross-session continuity (snapshot IDs), while all live session state is held in the Temporal workflow and accessed via queries. The gateway layer bridges synchronous Django code to the async Temporal world, polling queries until the session is ready.
