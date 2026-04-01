---
name: exploring-traces-mcp
description: >
  How to query, inspect, and debug LLM traces using PostHog's MCP tools.
  Use when the user asks to debug an AI agent trace, investigate LLM behavior,
  inspect token usage or costs, find why an agent made a decision, or explore
  AI/LLM observability data.
---

# Exploring LLM traces with MCP tools

PostHog captures LLM/AI agent activity as traces. Each trace is a tree of events representing
a single AI interaction — from the top-level agent invocation down to individual LLM API calls.

## Available tools

| Tool                                      | Purpose                                                  |
| ----------------------------------------- | -------------------------------------------------------- |
| `posthog:query-traces-list`               | Search and list traces by time range, properties, person |
| `posthog:query-trace`                     | Get a single trace by ID with all child events           |
| `posthog:execute-sql`                     | Ad-hoc SQL queries for complex trace analysis            |
| `posthog:get-llm-total-costs-for-project` | Aggregated LLM costs by model over time                  |

## Event schema

Traces are built from six `$ai_*` event types. All events in a trace share the same `$ai_trace_id`.

See the [event reference](./references/events-and-properties.md) for the full schema.

### Event hierarchy

```text
$ai_trace (top-level container)
  └── $ai_span (logical groupings, e.g. "RAG retrieval", "tool execution")
        ├── $ai_generation (individual LLM API call)
        ├── $ai_embedding (embedding creation)
        ├── $ai_metric (custom numeric metrics)
        └── $ai_feedback (human feedback)
```

The `$ai_parent_id` property links child events to their parent span or trace.

### Capture order

Events are captured bottom-up: `$ai_generation`/`$ai_embedding` first, then `$ai_span`, then `$ai_trace`.
The `$ai_trace` event is emitted last and contains the final `$ai_input_state` and `$ai_output_state`.

## Workflows

### 1. Find traces matching criteria

Use `query-traces-list` to search by time range, person, or properties:

```json
posthog:query-traces-list
{
  "dateRange": {"date_from": "-7d"},
  "limit": 20,
  "filterTestAccounts": true
}
```

Filter by properties to narrow results:

```json
posthog:query-traces-list
{
  "dateRange": {"date_from": "-1d"},
  "properties": [
    {"type": "event", "key": "$ai_model", "value": "gpt-4o", "operator": "exact"}
  ],
  "limit": 10
}
```

### 2. Inspect a single trace

Once you have a trace ID, use `query-trace` to get the full trace with all events:

```json
posthog:query-trace
{
  "traceId": "79955c94-7453-488f-a84a-eabb6f084e4c",
  "dateRange": {"date_from": "-30d"}
}
```

The response includes:

- `id`, `traceName`, `createdAt`, `distinctId`
- `totalLatency`, `inputTokens`, `outputTokens`
- `inputCost`, `outputCost`, `totalCost`
- `inputState`, `outputState` (application state — can be very large)
- `events[]` — array of all child events with their properties

### 3. Debug "what went wrong" in a trace

Follow this pattern to investigate a trace:

1. **Get the trace** with `query-trace` using the trace ID
2. **Scan the events** — look at the `event` field to identify generations, spans, and feedback
3. **Check generations** — each `$ai_generation` event has:
   - `$ai_input` — the messages sent to the LLM (system prompt, user messages, tool results)
   - `$ai_output_choices` — the LLM's response
   - `$ai_model` — which model was used
   - `$ai_input_tokens` / `$ai_output_tokens` — token counts
4. **Check spans** — `$ai_span` events show logical steps (RAG, tool calls, routing)
5. **Check feedback** — `$ai_feedback` events show human ratings

**Important:** The `$ai_input`, `$ai_input_state`, and `$ai_output_state` properties can be
extremely large (full conversation histories, system prompts, application state). When working
with these, dump the trace data to a file and use bash commands to explore it. Do not output
them directly into the conversation.

### 4. Search trace content with SQL

For complex searches (e.g. finding traces where specific text appeared in LLM input/output),
use `execute-sql`:

```sql
SELECT
    properties.$ai_trace_id AS trace_id,
    properties.$ai_model AS model,
    timestamp
FROM events
WHERE
    event = '$ai_generation'
    AND timestamp >= now() - INTERVAL 7 DAY
    AND properties.$ai_input ILIKE '%search term%'
ORDER BY timestamp DESC
LIMIT 20
```

### 5. Analyze costs and token usage

For aggregated cost analysis, use `get-llm-total-costs-for-project`:

```json
posthog:get-llm-total-costs-for-project
{
  "days": 7
}
```

For per-trace cost breakdown, use SQL:

```sql
SELECT
    properties.$ai_trace_id AS trace_id,
    sum(toFloat(properties.$ai_total_cost_usd)) AS total_cost,
    sum(toFloat(properties.$ai_input_tokens)) AS input_tokens,
    sum(toFloat(properties.$ai_output_tokens)) AS output_tokens
FROM events
WHERE
    event IN ('$ai_generation', '$ai_embedding')
    AND timestamp >= now() - INTERVAL 7 DAY
GROUP BY trace_id
ORDER BY total_cost DESC
LIMIT 20
```

### 6. Find traces by external identifiers

Customers often link traces to their own IDs (e.g. a project ID, conversation ID, or message ID).
These are typically stored as event properties or person properties. Use `read-data-schema` to
discover available properties, then filter:

```json
posthog:query-traces-list
{
  "dateRange": {"date_from": "-7d"},
  "properties": [
    {"type": "event", "key": "project_id", "value": "proj_abc123", "operator": "exact"}
  ]
}
```

Or via SQL for more flexibility:

```sql
SELECT DISTINCT properties.$ai_trace_id AS trace_id
FROM events
WHERE
    event IN ('$ai_trace', '$ai_generation')
    AND timestamp >= now() - INTERVAL 7 DAY
    AND properties.project_id = 'proj_abc123'
```

## Tips

- Always set `dateRange` — queries without a time range are slow and may time out
- Use `query-traces-list` first to find trace IDs, then `query-trace` for detail
- For the Lovable-style "paste a URL/ID and debug" workflow: extract the identifier, search
  for matching traces, then inspect the most relevant one
- The trace name (`traceName`) comes from `$ai_span_name` or `$ai_trace_name` on the `$ai_trace` event
- Use `filterTestAccounts: true` to exclude internal/test traffic
- When analyzing large traces, focus on the `events` array — each entry has `event` (type),
  `createdAt` (timestamp), and `properties` (all the `$ai_*` data)
