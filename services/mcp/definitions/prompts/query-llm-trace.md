Retrieve a single LLM trace by its trace ID. Returns the full trace including all child events (generations, spans, embeddings), total latency, token usage, costs, and input/output state. Use this tool to inspect a specific trace in detail — debugging errors, understanding agent decisions, and verifying LLM behavior.

Use `query-llm-traces-list` first to find trace IDs, then this tool to inspect a specific trace.

Use `read-data-schema` to discover available event properties for filtering (e.g. `$ai_model`, `$ai_provider`).

CRITICAL: Be minimalist. Only include filters and settings that are essential to answer the user's specific question. The `contentDetail` default of `"preview"` is usually sufficient.

# contentDetail parameter

Controls how much content is returned for large properties like `$ai_input`, `$ai_output_choices`, `$ai_input_state`, `$ai_output_state`:

- `"none"` — metadata only, shows `[N chars]` placeholders for large properties. Use for structural overview.
- `"preview"` (default) — first/last 300 chars of large properties with `... [N chars truncated] ...` in between. Usually enough to understand what happened.
- `"full"` — everything raw. Use when you need to read actual message content. WARNING: traces can be very large (100KB+). Dump results to a file and explore with bash commands.

# Data narrowing

## Property filters

Use property filters to narrow results within the trace. Only include property filters when they are essential to directly answer the user's question.

IMPORTANT: Do not check if a property is set unless the user explicitly asks for it.

When using a property filter, you should:

- **Prioritize properties directly related to the context or objective of the user's query.** Common AI properties include `$ai_model`, `$ai_provider`, `$ai_latency`, `$ai_input_tokens`, `$ai_output_tokens`, `$ai_total_cost_usd`, `$ai_is_error`, `$ai_http_status`, `$ai_span_name`.
- **Note:** `$ai_is_error` and `$ai_error` are valid filter properties but may not appear via `read-data-schema`. Use `$ai_is_error` with operator `exact` and value `["true"]` to find error events.
- **Ensure that you find both the property group and name.** Property groups should be one of the following: event, person, session, group.
- After selecting a property, **validate that the property value accurately reflects the intended criteria**.
- **Find the suitable operator for type** (e.g., `contains`, `is set`).
- If the operator requires a value, use the `read-data-schema` tool to find the property values.

Supported operators for the String type are:

- equals (exact)
- doesn't equal (is_not)
- contains (icontains)
- doesn't contain (not_icontains)
- matches regex (regex)
- doesn't match regex (not_regex)
- is set
- is not set

Supported operators for the Numeric type are:

- equals (exact)
- doesn't equal (is_not)
- greater than (gt)
- less than (lt)
- is set
- is not set

## Time period

You should not filter events by time using property filters. Instead, use the `dateRange` field. If the question doesn't mention time, use last 7 days as a default time period.

# Response shape

The trace result contains:

- `id` — unique trace ID
- `traceName` — name of the trace
- `createdAt` — timestamp of the first event
- `distinctId` — the person's distinct ID
- `aiSessionId` — session ID grouping related traces
- `totalLatency` — total latency in seconds
- `inputTokens` / `outputTokens` — token counts across all generations
- `inputCost` / `outputCost` / `totalCost` — costs in USD
- `inputState` / `outputState` — JSON application state (from the `$ai_trace` event)
- `errorCount` — number of errors in the trace
- `events` — list of child events. Each has `event` (type), `createdAt`, and `properties` with the full event data.

## Event types in the events array

- **`$ai_generation`** / **`$ai_embedding`** — an LLM or embedding API call. Key properties: `$ai_model`, `$ai_provider`, `$ai_input`, `$ai_output_choices`, `$ai_latency`, `$ai_input_tokens`, `$ai_output_tokens`, `$ai_total_cost_usd`, `$ai_is_error`, `$ai_error`.
- **`$ai_span`** — a unit of work within the trace (e.g. retrieval step, tool execution). Key properties: `$ai_span_name`, `$ai_input_state`, `$ai_output_state`, `$ai_latency`, `$ai_parent_id`.

All events share `$ai_trace_id` and use `$ai_parent_id` for tree structure.

# Debugging workflow

1. Fetch the trace with default `preview` contentDetail.
2. Scan the events array — identify generations, spans, errors.
3. For each generation, check `$ai_model`, token counts, `$ai_is_error`.
4. If you need to read actual message content, re-fetch with `contentDetail: "full"` and dump to a file.
5. The `_posthogUrl` in the response links to the trace in the PostHog UI.

# Examples

## Get a trace with default preview

```json
{
  "traceId": "79955c94-7453-488f-a84a-eabb6f084e4c",
  "dateRange": { "date_from": "-7d" }
}
```

## Get just the structure (no content)

```json
{
  "traceId": "79955c94-7453-488f-a84a-eabb6f084e4c",
  "dateRange": { "date_from": "-7d" },
  "contentDetail": "none"
}
```

## Get full content (dump to file)

```json
{
  "traceId": "79955c94-7453-488f-a84a-eabb6f084e4c",
  "dateRange": { "date_from": "-7d" },
  "contentDetail": "full"
}
```

# Reminders

- Always provide a `dateRange` — traces outside the range won't be found.
- Start with `preview` contentDetail and only escalate to `full` when you need to read actual message content.
- When using `contentDetail: "full"`, dump the results to a file and use bash commands to explore — do not output large trace content directly into the conversation.
- The `_posthogUrl` field links directly to the trace in the PostHog UI for manual verification.
