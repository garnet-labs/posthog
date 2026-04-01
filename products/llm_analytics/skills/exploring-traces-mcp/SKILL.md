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

| Tool                                      | Purpose                                                   |
| ----------------------------------------- | --------------------------------------------------------- |
| `posthog:query-llm-traces-list`           | Search and list traces (compact — no large content)       |
| `posthog:query-llm-trace`                 | Get a single trace by ID with configurable content detail |
| `posthog:execute-sql`                     | Ad-hoc SQL for complex trace analysis                     |
| `posthog:get-llm-total-costs-for-project` | Aggregated LLM costs by model over time                   |

## Content detail levels

`query-llm-trace` has a `contentDetail` parameter controlling how large properties are returned:

| Value                 | Behavior                                    | When to use                                  |
| --------------------- | ------------------------------------------- | -------------------------------------------- |
| `"none"`              | Shows `"[N chars]"` for large props         | Structural overview only                     |
| `"preview"` (default) | First/last 300 chars with truncation marker | Understanding what happened                  |
| `"full"`              | Everything raw                              | Reading actual messages (dump to file first) |

`query-llm-traces-list` always uses `"none"` internally for compact results.

## Event hierarchy

See the [event reference](./references/events-and-properties.md) for the full schema.

```text
$ai_trace (top-level container)
  └── $ai_span (logical groupings, e.g. "RAG retrieval", "tool execution")
        ├── $ai_generation (individual LLM API call)
        ├── $ai_embedding (embedding creation)
        ├── $ai_metric (custom numeric metrics)
        └── $ai_feedback (human feedback)
```

Events are captured bottom-up: `$ai_generation`/`$ai_embedding` first, then `$ai_span`, then `$ai_trace`.

## Workflows

### 1. Find traces

```json
posthog:query-llm-traces-list
{
  "dateRange": {"date_from": "-7d"},
  "filterTestAccounts": true,
  "limit": 20
}
```

Filter by model, provider, errors, or person:

```json
posthog:query-llm-traces-list
{
  "dateRange": {"date_from": "-1d"},
  "properties": [
    {"type": "event", "key": "$ai_model", "value": "gpt-4o", "operator": "exact"}
  ]
}
```

### 2. Inspect a single trace

```json
posthog:query-llm-trace
{
  "traceId": "79955c94-7453-488f-a84a-eabb6f084e4c",
  "dateRange": {"date_from": "-30d"}
}
```

To see full message content (dump to file first):

```json
posthog:query-llm-trace
{
  "traceId": "79955c94-7453-488f-a84a-eabb6f084e4c",
  "dateRange": {"date_from": "-30d"},
  "contentDetail": "full"
}
```

### 3. Debug "what went wrong"

1. **Get the trace** with `query-llm-trace` (default preview mode)
2. **Scan the events** — look at the `event` field to identify generations, spans, feedback
3. **Check generations** — each `$ai_generation` has `$ai_model`, `$ai_input`, `$ai_output_choices`, `$ai_is_error`
4. **Check spans** — `$ai_span` events show logical steps (RAG, tool calls, routing)
5. **Deep dive** — re-fetch with `contentDetail: "full"` for specific events if needed, dump to file

### 4. Search trace content with SQL

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

### 5. Analyze costs

For aggregated costs: `get-llm-total-costs-for-project`

For per-trace breakdown:

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

Customers often store their own IDs as event or person properties.
Use `read-data-schema` to discover available properties, then filter:

```json
posthog:query-llm-traces-list
{
  "dateRange": {"date_from": "-7d"},
  "properties": [
    {"type": "event", "key": "project_id", "value": "proj_abc123", "operator": "exact"}
  ]
}
```

## Tips

- Always set `dateRange` — queries without a time range are slow
- Use `query-llm-traces-list` first to find trace IDs, then `query-llm-trace` for detail
- Use `filterTestAccounts: true` to exclude internal/test traffic
- The `preview` content detail mode is usually enough to understand what happened
- Only use `contentDetail: "full"` when you need to read actual messages, and dump to file
