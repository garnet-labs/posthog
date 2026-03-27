# Event filters

Event filters let customers drop events at ingestion time based on event name or distinct ID. They run early in the Node.js ingestion pipeline, before transformations, so filtered events never reach Hog execution or Kafka output topics.

## Why this exists

Transformations that drop events are free for customers but still cost us ingestion and compute. There is no incentive for customers to avoid using transformations for filtering since they don't pay for dropped events. Transformations run arbitrary Hog code through a heavyweight execution path — a simple "drop events where name = X" goes through the same pipeline as a complex data transformation.

Event filters solve this by providing a purpose-built, declarative filtering mechanism that is cheaper to evaluate (boolean tree matching vs. Hog VM execution), earlier in the pipeline (runs before transformations, person processing, and cookieless rewriting), and easier to configure (visual tree builder in the UI, no code required).

## Features

### Boolean expression tree

The filter is a single boolean expression tree per team, not a flat list of rules. The tree supports AND, OR, NOT, and condition nodes at arbitrary depth. This was chosen over a simpler list-of-rules approach because it can express any boolean logic — blocklists (drop events matching X OR Y), allowlists (drop everything NOT matching X OR Y), and compound rules (drop events matching X AND Y) — all in one structure. The tree is stored as JSON in Postgres so it can be extended with new node types or operators without schema migrations.

### Condition matching

Conditions match against two fields available early in the ingestion pipeline: `event_name` (the event's name like `$pageview`) and `distinct_id` (the user/device identifier). These are the fields available in Kafka message headers before full event parsing, which is why they were chosen over property-level filtering. Two operators are supported: `exact` (string equality) and `contains` (substring match). `contains` is useful for patterns like "drop all events from distinct IDs containing `bot-`".

### Enable/disable toggle

The filter defaults to disabled. This is deliberate — you should be able to build and test a filter expression without it affecting live traffic. The toggle is prominent at the top of the page with a status card showing "Filter is active" or "Filter is disabled" and a description of what that means. The pipeline step only loads filters where `enabled = true` from Postgres, so disabled filters have zero runtime cost.

### Test cases

Test cases let you verify your filter expression against example events before enabling it. Each test case specifies an event (event_name, distinct_id) and the expected result (drop or ingest). They are evaluated client-side in real-time as you edit the expression — results update instantly without saving or hitting the API. This exists because filter misconfiguration can be catastrophic: an overly broad filter silently drops production data with no way to recover. Test cases are a safety net. They are persisted in the database alongside the filter so they survive page reloads and can be re-validated after editing. The filter cannot be enabled while any test case fails — the UI blocks the toggle and shows an error. If you save with tests failing while the filter is enabled, it auto-disables on save.

### Pruning

Users can create empty groups in the UI (an OR with no children, an AND containing only empty sub-groups). Rather than rejecting these on save or silently evaluating them (which could be dangerous — empty AND is vacuous true), we prune the tree on save. Empty groups are removed, single-child groups are collapsed to just the child, and NOT wrapping nothing is removed. This keeps the stored tree minimal and avoids edge cases in evaluation. The UI tells users that empty groups are removed on save.

### Metrics

When events are dropped, the pipeline step produces an `app_metrics2` entry to ClickHouse (`app_source: "event_filter"`, `metric_name: "dropped"`). This is recorded as a side effect of the drop, not an ingestion warning — because dropping is what the customer asked for, not a problem to warn about. The metrics are displayed on the filter page using the existing `AppMetricSummary` component (sparkline + count with period-over-period comparison). A note explains the counts are approximate since app_metrics2 aggregates by hour. The metrics API endpoints (`/metrics/` and `/metrics/totals/`) use the same `fetch_app_metrics_trends`/`fetch_app_metric_totals` functions as hog function metrics, querying ClickHouse with `app_source = "event_filter"` and the filter's UUID as `app_source_id`.

### Show expression

The "Show expression" button renders the filter tree as a readable text expression in a modal: `DROP WHERE event_name = "$pageview" OR (event_name = "$internal" AND distinct_id ~ "bot-")`. This exists because the visual tree builder, while easy to edit, can be hard to read at a glance for complex expressions. The text view uses `=` for exact match, `~` for contains, parentheses for groups, `AND`/`OR`/`NOT` keywords, and proper indentation. Operators are on their own lines for readability.

### Drag and drop

Conditions and groups can be reordered within a group by dragging. Items can also be moved between groups by dropping on a different group's droppable area (highlighted on hover). This uses `@dnd-kit` with `useSortable` for within-group reorder and `useDroppable` on each group for cross-group moves. Each node has a stable `_nid` (node ID) assigned on first render so that DnD IDs don't change when the tree mutates. Cross-group moves happen on drop (not during drag) to avoid stale state issues with React's render cycle.

### Form validation

The form validates on submit via kea-forms `errors`. Two checks: condition values cannot be empty (each empty input gets a red border after the first submit attempt), and the filter cannot be enabled without at least one condition leaf in the tree. The `showFilterFormErrors` flag from kea-forms controls when validation errors are displayed — they only appear after the first failed submit, not while the user is still building the expression.

## Limits

- **Max conditions** total across the tree (`MAX_CONDITIONS` in `event_filter_config.py`)
- **Max nesting depth** (`MAX_TREE_DEPTH` in `event_filter_config.py`)
- **Empty groups are pruned** on save (collapsed or removed)
- **Supported fields:** defined by `ALLOWED_FIELDS` in `event_filter_config.py` and the zod schema in `schema.ts`
- **Supported operators:** defined by `ALLOWED_OPERATORS` in `event_filter_config.py` and the zod schema in `schema.ts`

## Data model

One `EventFilterConfig` per team, stored in Postgres:

| Field         | Type               | Description                                   |
| ------------- | ------------------ | --------------------------------------------- |
| `id`          | UUID               | Primary key                                   |
| `team`        | OneToOne → Team    | One filter config per team                    |
| `enabled`     | boolean            | Whether the filter is active (default: false) |
| `filter_tree` | JSON (nullable)    | Boolean expression tree                       |
| `test_cases`  | JSON (default: []) | Test events with expected results             |
| `created_at`  | DateTime           | Auto                                          |
| `updated_at`  | DateTime           | Auto                                          |
| `created_by`  | FK → User          | Nullable                                      |

### Filter tree schema

The filter tree is a recursive boolean expression with four node types:

```json
Condition:  { "type": "condition", "field": "event_name"|"distinct_id", "operator": "exact"|"contains", "value": "<string>" }
AND:        { "type": "and", "children": [...nodes] }
OR:         { "type": "or", "children": [...nodes] }
NOT:        { "type": "not", "child": <node> }
```

An empty tree (null or `{type: "or", children: []}`) means no filtering. New filters default to a top-level empty OR.

### Test cases schema

```json
[ { "event_name": "<string>", "distinct_id": "<string>", "expected_result": "drop"|"ingest" } ]
```

Test cases are evaluated client-side against the filter tree in real-time. The filter cannot be enabled while any test case fails. They are persisted so the filter can be re-validated after editing.

## Architecture

### Pipeline integration

```text
Kafka → parseHeaders → eventRestrictions → parseEvent → resolveTeam
  → validateMetadata → validateProperties → dropOldEvents
  → ★ applyEventFilters ★
  → cookieless → overflow → prefetchPersons → hogTransformations → ...
```

The filter step sits in `post-team-preprocessing-subpipeline`, after team resolution (we need `team.id` to look up the filter) and after `dropOldEvents`, but before cookieless processing and transformations.

When an event matches the filter, the event is dropped (not written to any output topic) and an app_metrics2 entry is produced as a side effect (`app_source: "event_filter"`, `metric_name: "dropped"`).

### Config loading

`EventFilterManager` uses `BackgroundRefresher` to load all enabled filters from Postgres every 60 seconds. This is a single query that fetches all enabled rows (expected to be few teams initially).

On load, each row is validated with a zod schema (`EventFilterRowSchema`). Invalid rows are logged and skipped — they never cause evaluation errors.

The manager's `getFilter(teamId)` is non-blocking — it returns cached data via `tryGet()` or null if not yet loaded. It also returns null if the filter tree has no condition leaves (e.g., only empty groups).

### Evaluation safety

The evaluator is conservative: when in doubt, don't drop.

Empty AND (`{type: "and", children: []}`) returns **false** (not vacuous true). In JavaScript, `[].every(fn)` returns `true`, which would drop every event. We guard against this explicitly. Empty OR returns **false** (no children match). The `treeHasConditions` check in the manager rejects trees with no condition leaves, so they never reach evaluation.

This means a misconfigured empty tree will never drop events. Dropping is irreversible; not dropping just means unwanted events get through temporarily.

### Pruning

On save, the Django model runs `prune_filter_tree` which removes AND/OR nodes with no children (after recursive pruning), collapses single-child AND/OR nodes to just the child, and removes NOT wrapping nothing (NOT of a pruned-away child). This keeps the stored tree minimal. The UI shows a note that empty groups are removed on save.

## API

Single-object endpoint, auto-creates on first access:

| Method | URL                                                         | Description                |
| ------ | ----------------------------------------------------------- | -------------------------- |
| `GET`  | `/api/environments/{team_id}/event_filters/`                | Get the config             |
| `POST` | `/api/environments/{team_id}/event_filters/`                | Update the config (upsert) |
| `GET`  | `/api/environments/{team_id}/event_filters/metrics/`        | Time-series drop metrics   |
| `GET`  | `/api/environments/{team_id}/event_filters/metrics/totals/` | Aggregate drop totals      |

The metrics endpoints query the `app_metrics2` ClickHouse table with `app_source = "event_filter"`.

## Frontend

The UI lives at `/data-management/event-filters` (scene: `EventFilters` in the CDP product manifest). It is a single-page editor (one filter per team, no list view):

- **Status card** — shows whether the filter is active, toggle to enable/disable
- **Metrics** — drop count with sparkline from app_metrics2
- **Expression builder** — recursive tree with drag-and-drop (dnd-kit), AND/OR dropdown, negate, delete, add condition/group
- **Show expression** — modal showing the tree as a readable logical expression (`DROP WHERE event_name = "foo" OR (...)`)
- **Test cases** — JSON-style event editor with live evaluation, pass/fail badges, blocks enabling on failure

### Form validation

Empty condition values are flagged on submit (`status="danger"` on the input). Filter cannot be enabled without conditions. Filter cannot be enabled with failing test cases (auto-disabled on save if tests fail).

## File layout

### Node.js (`nodejs/src/ingestion/`)

```text
common/
├── event-filters/
│   ├── index.ts        — public exports
│   ├── schema.ts       — zod schemas + TypeScript types
│   ├── evaluate.ts     — evaluateFilterTree(), treeHasConditions()
│   ├── manager.ts      — EventFilterManager (BackgroundRefresher)
│   ├── schema.test.ts
│   ├── evaluate.test.ts
│   └── manager.test.ts
└── steps/
    └── apply-event-filters-step.ts — pipeline step

analytics/
├── post-team-preprocessing-subpipeline.ts — wires the step
├── joined-ingestion-pipeline.ts — passes deps
├── config/outputs.ts — APP_METRICS_OUTPUT definition
└── outputs.ts — APP_METRICS_OUTPUT constant
```

### Django (`posthog/`)

```text
models/event_filter_config.py — model, validation, pruning, evaluation
models/test/test_event_filter_config.py — tests
api/event_filter_config.py — viewset with metrics endpoints
scopes.py — "event_filter" API scope
migrations/1068_event_filter_config.py
```

### Frontend (`frontend/src/scenes/data-pipelines/`)

```text
EventFilterScene.tsx — main UI (editor, DnD, metrics, test cases)
eventFilterLogic.ts — kea logic (form, actions, selectors, evaluation)
```

## Testing

### Integration test script

`bin/test-event-filters` — end-to-end test that configures a filter via the API, sends events through capture (`/i/v0/e`), polls app_metrics2 to verify drops, and uses baseline + delta to isolate counts from previous runs.

```bash
bin/test-event-filters --api-key <personal_api_key> [--capture-host http://localhost:3307]
```

### Unit tests

- **Python** (27 tests): `pytest posthog/models/test/test_event_filter_config.py` — evaluation, pruning, tree_has_conditions
- **Node.js** (42 tests): `pnpm test -- event-filters` — schema validation, evaluation, manager behavior

## Known limitations

- **Two fields only:** `event_name` and `distinct_id`. No property-level filtering, no timestamp, no session_id.
- **No feature flag gate yet.** The UI is visible to all users. A feature flag should be added before production rollout.
- **Metrics are approximate.** app_metrics2 aggregates by hour and may lose a small percentage of counts under high load.
- **60-second config propagation.** After saving a filter, it takes up to 60 seconds for the BackgroundRefresher to pick up the change. There is no push-based invalidation.
- **One filter per team.** The model is a OneToOneField on Team. Multiple independent filter sets per team are not supported.
