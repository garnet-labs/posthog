# ai_events: Remove preview columns and heavy property access from list views

## What changed

1. **Removed materialized preview columns** (`input_preview`, `output_choices_preview`) from the ClickHouse table definition, HogQL schema, property rewriter, taxonomy, and frontend renderers.

2. **Removed heavy column access from the traces list query.** The `events` tuple in `TracesQueryRunner` was narrowed from `tuple(uuid, event, timestamp, properties, input, output, output_choices, input_state, output_state, tools)` to `tuple(uuid, event, timestamp, properties)`. The trace-level `input_state` / `output_state` aggregations were also removed.

3. **Single-trace queries are unchanged.** `TraceQueryRunner` (trace detail view) and the evaluation runner still read all heavy columns.

## Why

### Preview columns were premature

The `input_preview` and `output_choices_preview` columns were MATERIALIZED expressions that truncated the first/last message to 200 chars at insert time. In practice:

- The frontend already has lazy-loading cells (`AIInputCell`, `AIOutputCell`) that fetch and render input/output on demand via `useAIData`, making server-side previews redundant.
- MATERIALIZED columns still occupy disk space and increase insert CPU cost, even if never queried.
- The truncation logic (JSON array indexing in ClickHouse SQL) was fragile and hard to evolve compared to client-side rendering.

### Heavy columns don't belong in list views

The traces list query aggregates across all events in a trace. Including `input`, `output`, `output_choices`, `input_state`, `output_state`, and `tools` in the `groupArrayIf` tuple meant ClickHouse was reading and shuffling megabytes of JSON per trace just to build the list view — data that was never displayed.

The `TraceMapperMixin._map_event()` code already handled the case where heavy columns are absent (the `*heavy` splat produces an empty list, and `merge_heavy_properties` with an empty dict is a no-op), so no mapper changes were needed.

Similarly, `_map_trace()` already used `.get()` for `input_state` / `output_state`, returning None when absent.

## What was removed

| Layer             | Removed                                                                           |
| ----------------- | --------------------------------------------------------------------------------- |
| ClickHouse DDL    | `input_preview` and `output_choices_preview` MATERIALIZED columns                 |
| HogQL schema      | `input_preview` and `output_choices_preview` field definitions                    |
| Property rewriter | `$ai_input_preview` and `$ai_output_choices_preview` mappings                     |
| Traces query      | Heavy columns from events tuple, `input_state`/`output_state` aggregations        |
| Taxonomy          | `$ai_input_preview` and `$ai_output_choices_preview` entries (Python + JSON)      |
| Frontend          | `showInputOutput` parameter, preview column renderers, preview `findIndex` checks |

## What was kept

- **`TraceQueryRunner`** — single-trace view needs full heavy column access for the detail panel.
- **Evaluation runner** — fetches a single event's properties for scoring.
- **`merge_heavy_properties` in utils.py** — still used by the single-trace path.
- **`input`/`output`/`output_choices`/`input_state`/`output_state`/`tools` columns in the table** — still written at insert time and available for single-trace reads.
