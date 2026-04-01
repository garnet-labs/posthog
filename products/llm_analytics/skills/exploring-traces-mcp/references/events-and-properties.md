# LLM analytics event and property reference

## Event types

### `$ai_trace`

Top-level container for a trace. Emitted last, after all child events.

| Property           | Type   | Description                                                  |
| ------------------ | ------ | ------------------------------------------------------------ |
| `$ai_trace_id`     | string | Unique trace identifier — shared by all events in this trace |
| `$ai_trace_name`   | string | Name of the trace (e.g. "ChatBot Interaction")               |
| `$ai_session_id`   | string | Groups multiple traces into a session                        |
| `$ai_input_state`  | JSON   | Application state at trace start (can be very large)         |
| `$ai_output_state` | JSON   | Application state at trace end (can be very large)           |
| `$ai_latency`      | float  | Total trace duration in seconds                              |

### `$ai_span`

Logical grouping within a trace (e.g. "RAG retrieval", "tool execution", "routing").

| Property           | Type   | Description                |
| ------------------ | ------ | -------------------------- |
| `$ai_trace_id`     | string | Parent trace ID            |
| `$ai_span_id`      | string | Unique span identifier     |
| `$ai_span_name`    | string | Name of this span          |
| `$ai_parent_id`    | string | ID of parent span or trace |
| `$ai_latency`      | float  | Span duration in seconds   |
| `$ai_input_state`  | JSON   | State entering this span   |
| `$ai_output_state` | JSON   | State leaving this span    |

### `$ai_generation`

Individual LLM API call (e.g. a chat completion request).

| Property              | Type       | Description                                                                                                                                 |
| --------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `$ai_trace_id`        | string     | Parent trace ID                                                                                                                             |
| `$ai_parent_id`       | string     | ID of parent span or trace                                                                                                                  |
| `$ai_model`           | string     | Model identifier (e.g. "gpt-4o", "claude-sonnet-4-20250514")                                                                                |
| `$ai_provider`        | string     | Provider name (e.g. "openai", "anthropic")                                                                                                  |
| `$ai_input`           | JSON array | Input messages — array of `{role, content}` objects. Can include system prompts, tool results, conversation history. **Can be very large.** |
| `$ai_output_choices`  | JSON array | LLM response — array of `{message: {role, content}}` objects. May include tool calls.                                                       |
| `$ai_input_tokens`    | int        | Tokens in the input                                                                                                                         |
| `$ai_output_tokens`   | int        | Tokens in the output                                                                                                                        |
| `$ai_input_cost_usd`  | float      | Cost of input tokens in USD                                                                                                                 |
| `$ai_output_cost_usd` | float      | Cost of output tokens in USD                                                                                                                |
| `$ai_total_cost_usd`  | float      | Total cost in USD                                                                                                                           |
| `$ai_latency`         | float      | Generation duration in seconds                                                                                                              |
| `$ai_http_status`     | int        | HTTP status from the LLM API                                                                                                                |
| `$ai_is_error`        | boolean    | Whether the generation errored                                                                                                              |
| `$ai_error`           | string     | Error message if generation failed                                                                                                          |
| `$ai_base_url`        | string     | LLM API base URL                                                                                                                            |
| `$ai_tool_calls`      | JSON array | Tool calls made by the LLM                                                                                                                  |
| `$ai_tools_available` | JSON array | Tools available to the LLM                                                                                                                  |

### `$ai_embedding`

Embedding creation event (text to vector).

| Property             | Type   | Description                |
| -------------------- | ------ | -------------------------- |
| `$ai_trace_id`       | string | Parent trace ID            |
| `$ai_parent_id`      | string | ID of parent span or trace |
| `$ai_model`          | string | Embedding model identifier |
| `$ai_provider`       | string | Provider name              |
| `$ai_input_tokens`   | int    | Tokens processed           |
| `$ai_input_cost_usd` | float  | Cost in USD                |
| `$ai_total_cost_usd` | float  | Total cost in USD          |
| `$ai_latency`        | float  | Duration in seconds        |

### `$ai_feedback`

Human feedback on a trace or generation.

| Property              | Type          | Description                                     |
| --------------------- | ------------- | ----------------------------------------------- |
| `$ai_trace_id`        | string        | Trace this feedback applies to                  |
| `$ai_parent_id`       | string        | Specific event this feedback applies to         |
| `$ai_feedback_rating` | string/number | Rating value (e.g. "positive", "negative", 1-5) |
| `$ai_feedback_text`   | string        | Freeform feedback text                          |

### `$ai_metric`

Custom numeric metric captured on a trace.

| Property           | Type   | Description                           |
| ------------------ | ------ | ------------------------------------- |
| `$ai_trace_id`     | string | Parent trace ID                       |
| `$ai_parent_id`    | string | Specific event this metric applies to |
| `$ai_metric_name`  | string | Name of the metric                    |
| `$ai_metric_value` | float  | Metric value                          |

## Common property patterns

### Linking events in a trace

All events share `$ai_trace_id`. The hierarchy is built via `$ai_parent_id`:

```text
$ai_trace (id: "trace-1", $ai_trace_id: "trace-1")
  └── $ai_span (id: "span-1", $ai_trace_id: "trace-1", $ai_parent_id: "trace-1")
        └── $ai_generation (id: "gen-1", $ai_trace_id: "trace-1", $ai_parent_id: "span-1")
```

### Cost aggregation

Costs are only on `$ai_generation` and `$ai_embedding` events.
To get total trace cost, sum `$ai_total_cost_usd` across these events for the same `$ai_trace_id`.

### Latency calculation

If all events with latency are generations (no spans with latency), sum all generation latencies.
Otherwise, sum latency only from direct children of the trace (where `$ai_parent_id` equals `$ai_trace_id`).

### Large properties warning

These properties can contain megabytes of data:

- `$ai_input` — full conversation history, system prompts
- `$ai_input_state` / `$ai_output_state` — application state snapshots

When querying these, either:

- Select only the fields you need
- Dump results to a file and explore with bash commands
- Use `SUBSTRING()` or `LENGTH()` in SQL to preview without loading full content
