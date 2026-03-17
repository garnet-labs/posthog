# ai_events: Remove list view routing, keep single-trace only

## What changed

Removed all `ai_events` table routing from list views (traces list, errors tab, tools tab, generations list). Only single-trace contexts (trace detail, neighbors, evaluation runs/summary) still route to `ai_events`.

Deleted `AiEventsQuery` — a new query node kind that existed solely for the generations list to transparently choose between `ai_events` and `events`. With list views on `events`, the entire node kind, its runner, its schema plumbing, and all frontend wiring became dead code.

## Why

List views never access heavy columns (`$ai_input`, `$ai_output`, `$ai_tools`, etc.) — they aggregate metadata (tokens, costs, latency, error counts). These aggregations work fine against the `events` table using `properties.$ai_*` with materialized columns.

The routing added significant complexity for zero benefit on list views:

- Two AST rewriter invocations per query (forward + reverse)
- Feature flag conditionals in 3 frontend logic files and 1 query runner
- A full `AiEventsQuery` node kind with its own runner, schema interface, and union memberships across ~15 type definitions
- Dual SQL templates for errors and tools tabs

## What was removed

| Layer           | Removed                                                                             |
| --------------- | ----------------------------------------------------------------------------------- |
| Backend         | `AiEventsQueryRunner`, `validate_ai_event_names()`                                  |
| Backend         | Routing logic in `TracesQueryRunner` (reverted to master)                           |
| Backend         | `AiEventsQuery` dispatch in `query_runner.py`                                       |
| Frontend schema | `AiEventsQuery` enum value, interface, and all union memberships                    |
| Frontend logic  | Feature flag wiring in errors, tools, and generations logics                        |
| Frontend utils  | `AiEventsQuery` from `isEventsQuery()`, `dataTableLogic`, `DataTable/utils`         |
| SQL templates   | `errors_events.sql` and `tools_events.sql` (fallback copies)                        |
| SQL templates   | `errors.sql` and `tools.sql` reverted to `FROM events` with `properties.$ai_*`      |
| Generated       | `schema.py`, `schema.json`, MCP types regenerated                                   |
| Tests           | `test_ai_events_query_runner.py`, `validate_ai_event_names` tests, snapshot updates |

## What was kept

- **`TraceQueryRunner`** — single trace detail, routes to `ai_events` with rewriter fallback
- **`TraceNeighborsQueryRunner`** — older/newer navigation, same routing
- **`evaluation_runs.py` / `evaluation_summary.py`** — dual-path for eval scoring
- **Rewriter infrastructure** — `AiPropertyRewriter`, `AiColumnRewriter`, `ai_table_resolver`
- **Table infrastructure** — DDL, MV, HogQL schema, migration, Kafka topic, write-side split
- **Frontend rendering** — preview column renderers, `normalizeMessage`, display components
- **Feature flag constant** — `LLM_ANALYTICS_AI_EVENTS_TABLE_ROLLOUT` (backend routing still uses it)
