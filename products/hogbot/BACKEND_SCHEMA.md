# Hogbot Backend Schema

This document describes the API endpoints
and how they connect to the sandbox session managed by Temporal.

For the full Temporal workflow architecture, see `backend/ARCHITECTURE.md`.

## Session Lifecycle

There are no Django models for sessions or documents.
The sandbox filesystem and S3 logs are the source of truth.
The only persisted model is `HogbotRuntime` (one row per team)
which stores the latest snapshot external ID for session continuity.

When a message is sent, the API viewset calls `get_or_start_hogbot()`
from `products.hogbot.backend.gateway`. This either:

- attaches to the already-running Temporal workflow for the team, or
- starts a new `hogbot` workflow that provisions a sandbox and starts the HTTP server

The gateway polls the workflow's `get_connection_info` query until `ready=True`,
then returns a `HogbotConnectionInfo` with the `server_url` and `connect_token`.
The API viewset uses these to forward messages directly to the sandbox HTTP server.

## Log Format

Hogbot uses the same log format as the Tasks product.
Logs are stored as JSONL in S3, one JSON object per line,
following the ACP (Agent Communication Protocol) notification format.

The frontend reuses `parseLogs`
from `products/tasks/frontend/lib/parse-logs.ts`.

### Two Log Files

| Agent    | S3 key pattern                                  | API path                               |
| -------- | ----------------------------------------------- | -------------------------------------- |
| Admin    | `hogbot/{team_id}/admin.jsonl`                  | `/hogbot/admin/logs/`                  |
| Research | `hogbot/{team_id}/research/{research_id}.jsonl` | `/hogbot/research/{research_id}/logs/` |

### Frontend Polling

The frontend polls the admin agent's S3 log endpoint every 2 seconds.
Each poll fetches the full JSONL file and re-parses with `parseLogs()`.
State only updates when the content changes (string equality check)
so polling doesn't cause UI flicker.

### Log Entry Types

| Type      | Rendered As                                              |
| --------- | -------------------------------------------------------- |
| `agent`   | Chat message bubble (left-aligned, from Hogbot)          |
| `user`    | Chat message bubble (right-aligned, from user)           |
| `tool`    | Collapsible tool call (inside "Thinking" section)        |
| `console` | Console log with level badge (inside "Thinking" section) |
| `system`  | Italic system text (inside "Thinking" section)           |
| `raw`     | Monospace raw text (inside "Thinking" section)           |

## API Endpoints

### Admin Agent Logs

**`GET /api/projects/:team_id/hogbot/admin/logs/`**

Returns raw JSONL log text from S3 for the admin agent.
Proxies S3 to avoid CORS (same pattern as Tasks `runs/{id}/logs/`).

Response: plain text (JSONL format).

### Send Message

**`POST /api/projects/:team_id/hogbot/send-message/`**

Sends a message to Hogbot. The endpoint:

1. Calls `get_or_start_hogbot()` to ensure the sandbox session is running
2. Forwards the message to the sandbox HTTP server at the appropriate route

Both message types are delivered to the agents inside the sandbox — the
sandbox server is responsible for routing to the correct agent loop.

**User message** — forwarded to `POST {sandbox_url}/admin/message`,
routed to the admin agent:

```json
{
  "type": "user_message",
  "content": "Can you analyze our funnel?"
}
```

**Signal** — forwarded to `POST {sandbox_url}/research/signal`,
routed to the research agent:

```json
{
  "type": "signal",
  "signal": {
    "product": "signals",
    "document_type": "issue_fingerprint",
    "model_name": "text-embedding-3-small-1536",
    "rendering": "plain",
    "document_id": "abc-123",
    "timestamp": "2026-03-25T10:00:00Z",
    "content": "The text content that was embedded",
    "metadata": "{}"
  }
}
```

Signals match the `document_embeddings` table shape
(`SELECT * FROM document_embeddings WHERE model_name = 'text-embedding-3-small-1536' AND product = 'signals' ORDER BY timestamp DESC`).

Response: `202 Accepted` on success, `503 Service Unavailable` if the
sandbox session is not ready or the forward fails.

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

## Sandbox HTTP Server Contract

The sandbox runs an HTTP server started by the Temporal workflow.
The API viewset forwards messages to it using the `server_url` and
`connect_token` from `HogbotConnectionInfo`.

### Expected sandbox endpoints

| Method | Path               | Agent    | Purpose                                   |
| ------ | ------------------ | -------- | ----------------------------------------- |
| POST   | `/admin/message`   | Admin    | Deliver a user chat message               |
| POST   | `/research/signal` | Research | Deliver a document_embeddings signal      |
| GET    | `/health`          | —        | Health check (used during server startup) |

Authentication: `Authorization: Bearer {connect_token}` when the
sandbox backend requires it (Modal). Docker sandboxes may not need it.

## Backend Implementation Checklist

- [x] Create viewset with admin/logs, send-message, files, files/read endpoints
- [x] Register viewset in `posthog/api/__init__.py`
- [x] Wire send-message to `get_or_start_hogbot()` gateway
- [x] Forward user_message to sandbox `/admin/message`
- [x] Forward signal to sandbox `/research/signal`
- [ ] Add `HOGBOT = "hogbot"` to `Task.OriginProduct` in `products/tasks/backend/models.py`
- [ ] Replace stub log data with S3 reads (`object_storage.read`)
- [ ] Replace stub file listing with sandbox filesystem proxy
- [ ] Implement research agent log endpoint (per research ID)
- [ ] Implement sandbox server endpoints (`/admin/message`, `/research/signal`, `/health`)
