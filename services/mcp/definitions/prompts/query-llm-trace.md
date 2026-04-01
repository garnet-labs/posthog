Retrieve a single LLM trace by its trace ID. Returns the full trace including all child events (generations, spans, embeddings), total latency, token usage, costs, and input/output state.

Use `query-llm-traces-list` first to find trace IDs, then this tool to inspect a specific trace in detail.

## contentDetail parameter

Controls how much content is returned for large properties like `$ai_input`, `$ai_output_choices`, `$ai_input_state`, `$ai_output_state`:

- `"none"` — metadata only, shows `[N chars]` placeholders for large properties. Use for structural overview.
- `"preview"` (default) — first/last 300 chars of large properties with `... [N chars truncated] ...` in between. Usually enough to understand what happened.
- `"full"` — everything raw. Use when you need to read actual message content. WARNING: traces can be very large (100KB+). Dump results to a file and explore with bash commands.

## Response shape

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

## Debugging workflow

1. Fetch the trace with default `preview` contentDetail.
2. Scan the events array — identify generations, spans, errors.
3. For each generation, check `$ai_model`, token counts, `$ai_is_error`.
4. If you need to read actual message content, re-fetch with `contentDetail: "full"` and dump to a file.
5. The `_posthogUrl` in the response links to the trace in the PostHog UI.

## Examples

### Get a trace with default preview

```json
{
  "traceId": "79955c94-7453-488f-a84a-eabb6f084e4c",
  "dateRange": { "date_from": "-7d" }
}
```

### Get just the structure (no content)

```json
{
  "traceId": "79955c94-7453-488f-a84a-eabb6f084e4c",
  "dateRange": { "date_from": "-7d" },
  "contentDetail": "none"
}
```

### Get full content (dump to file)

```json
{
  "traceId": "79955c94-7453-488f-a84a-eabb6f084e4c",
  "dateRange": { "date_from": "-7d" },
  "contentDetail": "full"
}
```
