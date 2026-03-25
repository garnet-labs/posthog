# Hogbot Backend Schema

This document describes the expected API endpoints, data models,
and agent architecture for the Hogbot backend.

## API Endpoints

### Messages

**`GET /api/projects/:team_id/hogbot/messages/`**

List chat messages between the user and the agent.

Response:
```json
{
    "results": [
        {
            "id": "uuid",
            "role": "user" | "agent" | "system",
            "type": "text" | "proactive",
            "content": "string (markdown)",
            "created_at": "2026-03-25T10:00:00Z"
        }
    ]
}
```

**`POST /api/projects/:team_id/hogbot/messages/`**

Send a message from the user to the agent.

Request:
```json
{
    "content": "string"
}
```

Response: returns the created user message object (same shape as above).
The agent response will arrive asynchronously via SSE.

**`GET /api/projects/:team_id/hogbot/messages/stream/`**

SSE endpoint for real-time message delivery.
Streams new messages (including proactive agent messages) as they are created.

Event format:
```
event: message
data: {"id": "uuid", "role": "agent", "type": "proactive", "content": "...", "created_at": "..."}
```

### Research Documents

**`GET /api/projects/:team_id/hogbot/research/`**

List research documents (markdown files from the sandbox).

Response:
```json
{
    "results": [
        {
            "id": "uuid",
            "filename": "mobile-retention-drop.md",
            "title": "Mobile retention drop investigation",
            "content": "# Full markdown content...",
            "created_at": "2026-03-25T10:05:00Z",
            "updated_at": "2026-03-25T10:30:00Z"
        }
    ]
}
```

**`GET /api/projects/:team_id/hogbot/research/:id/`**

Get a single research document by ID.

### Tasks

Tasks are managed by the existing Tasks product.
Filter by `origin_product=hogbot`:

**`GET /api/projects/:team_id/tasks/?origin_product=hogbot`**

Uses the existing `TaskViewSet` — no new endpoint needed.
Requires adding `HOGBOT = "hogbot"` to `Task.OriginProduct` choices
in `products/tasks/backend/models.py`.

## Data Models

### HogbotMessage

```python
class HogbotMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user"
        AGENT = "agent"
        SYSTEM = "system"

    class Type(models.TextChoices):
        TEXT = "text"
        PROACTIVE = "proactive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    team = models.ForeignKey("posthog.Team", on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=Role.choices)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.TEXT)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "posthog_hogbot_message"
        ordering = ["created_at"]
```

### ResearchDocument

```python
class ResearchDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    team = models.ForeignKey("posthog.Team", on_delete=models.CASCADE)
    sandbox_id = models.CharField(max_length=255, null=True, blank=True)
    filename = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "posthog_hogbot_research_document"
        ordering = ["-updated_at"]
```

## Agent Architecture

Hogbot runs two concurrent Claude SDK agent loops inside a cloud sandbox:

### 1. Research Agent

- Runs continuously in the background
- Analyzes product data using PostHog MCP tools
- Creates and updates research documents (markdown files) in the sandbox
- Creates Tasks (via the Tasks product API) with `origin_product="hogbot"`
- Can send proactive messages to the user when it discovers insights

### 2. Admin Agent

- Handles user chat interactions
- Receives user messages and generates responses
- Can delegate work to the research agent
- Manages the overall Hogbot session state

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

### Message Streaming

Proactive messages and agent responses stream to the frontend via SSE:

1. Agent writes a message inside the sandbox
2. Sandbox posts the message to the Hogbot API
   (authenticated via connection token)
3. Backend writes the message to a Redis stream
   (reference: `products/tasks/backend/temporal/process_task/activities/relay_sandbox_events.py`)
4. Django SSE endpoint reads from Redis stream
   and pushes to the connected frontend client
5. Frontend appends the message to the chat

### OAuth & MCP Access

The sandbox receives a scoped OAuth token
(reference: `products/tasks/backend/temporal/oauth.py`)
that grants access to PostHog MCP tools.
The research agent uses these tools to query insights, funnels,
retention data, and other PostHog product data.

## Backend Implementation Checklist

- [ ] Add `HOGBOT = "hogbot"` to `Task.OriginProduct` in `products/tasks/backend/models.py`
- [ ] Create `HogbotMessage` model in `products/hogbot/backend/models.py`
- [ ] Create `ResearchDocument` model in `products/hogbot/backend/models.py`
- [ ] Create serializers in `products/hogbot/backend/presentation/serializers.py`
- [ ] Create viewsets in `products/hogbot/backend/presentation/views.py`
- [ ] Register URLs in `products/hogbot/backend/presentation/urls.py`
- [ ] Create Temporal workflow for sandbox provisioning
- [ ] Implement SSE endpoint for message streaming
- [ ] Create agent server entrypoint with research + admin loops
- [ ] Add Django migration for new models
- [ ] Add `hogbot` to `INSTALLED_APPS` in settings
