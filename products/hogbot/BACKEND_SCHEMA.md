# Hogbot Backend Schema

This document describes the expected API endpoints
and agent architecture for the Hogbot backend.

There are no Django models for sessions or documents —
the sandbox filesystem and S3 logs are the source of truth.

## Log Format

Hogbot uses the same log format as the Tasks product.
Logs are stored as JSONL in S3, with each line being a JSON object
following the ACP (Agent Communication Protocol) notification format.

The frontend reuses `parseLogs`
from `products/tasks/frontend/lib/parse-logs.ts`.

### Two Log Files

| Agent | S3 key pattern | API path |
|-------|---------------|----------|
| Admin | `hogbot/{team_id}/admin.jsonl` | `/hogbot/admin/logs/` |
| Research | `hogbot/{team_id}/research/{research_id}.jsonl` | `/hogbot/research/{research_id}/logs/` |

The admin agent writes to a single known S3 file per team.
The research agent writes one log file per research task.

### Frontend Polling

The frontend polls the admin agent's S3 log endpoint every 2 seconds.
Each poll fetches the full JSONL file, parses it with `parseLogs()`,
and re-derives the chat blocks. No SSE or Redis is involved —
the S3 file is the single source of truth.

When a user sends a message, the frontend POSTs to the message endpoint
and immediately triggers a poll to pick up the response faster.

### Log Entry Types

| Type | Rendered As |
|------|-------------|
| `agent` | Chat message bubble (left-aligned, from Hogbot) |
| `user` | Chat message bubble (right-aligned, from user) |
| `tool` | Collapsible tool call (inside "Thinking" section) |
| `console` | Console log with level badge (inside "Thinking" section) |
| `system` | Italic system text (inside "Thinking" section) |
| `raw` | Monospace raw text (inside "Thinking" section) |

The frontend groups consecutive non-message entries (tool, console, system, raw)
into collapsible "Thinking" sections between chat messages.
These are collapsed by default.

## API Endpoints

### Admin Agent

**`GET /api/projects/:team_id/hogbot/admin/logs/`**

Returns raw JSONL log text from S3 for the admin agent.
Proxies S3 to avoid CORS (same pattern as Tasks `runs/{id}/logs/`).

Response: plain text (JSONL format, one JSON object per line).

**`POST /api/projects/:team_id/hogbot/admin/messages/`**

Send a user message to the admin agent.

Request:
```json
{
    "content": "string"
}
```

Response: `202 Accepted`.
The agent appends its response to the S3 log file.
The frontend picks it up on the next poll.

### Sandbox Filesystem

**`GET /api/projects/:team_id/hogbot/files/`**

List files on the sandbox filesystem.
Accepts an optional `glob` query parameter to filter (e.g. `/research/*.md`).

Response:
```json
{
    "results": [
        {
            "path": "/research/mobile-retention-drop.md",
            "filename": "mobile-retention-drop.md",
            "size": 1240,
            "modified_at": "2026-03-25T10:30:00Z"
        }
    ]
}
```

**`GET /api/projects/:team_id/hogbot/files/read/`**

Read a single file from the sandbox filesystem.
Accepts a `path` query parameter.

Response: plain text (file content).

### Research Agent Logs

**`GET /api/projects/:team_id/hogbot/research/:research_id/logs/`**

Returns raw JSONL log text from S3 for a specific research agent run.
Same format as admin logs.

### Tasks

Tasks are managed by the existing Tasks product.
Filter by `origin_product=hogbot`:

**`GET /api/projects/:team_id/tasks/?origin_product=hogbot`**

Uses the existing `TaskViewSet` — no new endpoint needed.
Requires adding `HOGBOT = "hogbot"` to `Task.OriginProduct` choices
in `products/tasks/backend/models.py`.

## Agent Architecture

Hogbot runs two concurrent Claude SDK agent loops inside a cloud sandbox.
Both agents append their logs to S3 as JSONL.

### 1. Admin Agent

- Handles user chat interactions
- Receives user messages and generates responses
- Can delegate work to the research agent
- Appends logs to `hogbot/{team_id}/admin.jsonl`

### 2. Research Agent

- Runs continuously in the background
- Analyzes product data using PostHog MCP tools
- Creates and updates markdown files on the sandbox filesystem
  (e.g. `/research/mobile-retention-drop.md`)
- Creates Tasks (via the Tasks product API) with `origin_product="hogbot"`
- Appends per-research logs to `hogbot/{team_id}/research/{research_id}.jsonl`
- Can send proactive messages via the admin agent

### Sandbox Provisioning

Follow the existing Tasks product pattern:

1. **Temporal workflow** orchestrates the sandbox lifecycle
   (reference: `products/tasks/backend/temporal/process_task/workflow.py`)
2. **Sandbox provider** (Docker for local, Modal for production)
   creates an isolated environment
   (reference: `products/tasks/backend/services/sandbox.py`)
3. **Connection token** (JWT RS256, 24h expiry)
   authenticates sandbox-to-API communication
   (reference: `products/tasks/backend/services/connection_token.py`)
4. The sandbox runs an agent server (`npx agent-server`)
   that hosts both agent loops

### Log Persistence

1. Agent activity inside the sandbox produces ACP notifications
2. The agent server appends each event as a JSON line to the S3 log file
3. The frontend polls the S3 log proxy endpoint every 2 seconds
4. Each poll re-parses the full file and updates the UI

### OAuth & MCP Access

The sandbox receives a scoped OAuth token
(reference: `products/tasks/backend/temporal/oauth.py`)
that grants access to PostHog MCP tools.
The research agent uses these tools to query insights, funnels,
retention data, and other PostHog product data.

## Backend Implementation Checklist

- [ ] Add `HOGBOT = "hogbot"` to `Task.OriginProduct` in `products/tasks/backend/models.py`
- [ ] Create sandbox filesystem proxy endpoints (list files, read file)
- [ ] Create admin agent S3 log proxy endpoint
- [ ] Create admin agent message endpoint (POST)
- [ ] Create research agent S3 log proxy endpoint (per research ID)
- [ ] Register URLs in `products/hogbot/backend/presentation/urls.py`
- [ ] Create Temporal workflow for sandbox provisioning
- [ ] Create agent server entrypoint with admin + research loops
- [ ] Add `hogbot` to `INSTALLED_APPS` in settings
