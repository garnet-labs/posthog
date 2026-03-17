# ai_events ClickHouse schema: Nullable columns, no defaults, no codecs

## What changed

All extracted AI property columns in the `ai_events` ClickHouse table are now `Nullable` instead of non-nullable with explicit defaults (`DEFAULT ''` / `DEFAULT 0`). Column-level `CODEC(ZSTD(3))` specifications were also removed.

## Why

### Defaults changed query semantics

On the existing `events` table, accessing a missing property like `properties.$ai_model` goes through HogQL's JSON extraction path which wraps the result in `nullIf(nullIf(JSONExtractRaw(...), ''), 'null')` — returning **NULL** for absent properties.

On `ai_events`, the `AiPropertyRewriter` rewrites `properties.$ai_model` directly to the `model` column. With a non-nullable column defaulting to `''`, missing properties silently became empty strings (or `0` for numerics) instead of NULL. This is a semantic change with real consequences:

- `avg(input_tokens)` gets deflated by 0s from events that genuinely don't have token data (e.g. `$ai_trace` events), instead of those rows being excluded
- Display shows "0 tokens" instead of nothing/dash for events without token info
- Filtering requires `!= ''` instead of the more natural `IS NOT NULL`

### Codecs are unnecessary

The ClickHouse team confirmed that server-level compression settings are sufficient. Column-level codec overrides should only be used for specific encodings like DoubleDelta, not general compression.

### Explicit defaults were redundant anyway

ClickHouse already defaults non-nullable `String` to `''` and `Int64` to `0`. The explicit `DEFAULT` clauses added no behavioral difference over the implicit type defaults.

## Design decisions

- **Core fields stay non-nullable**: `uuid`, `event`, `timestamp`, `team_id`, `distinct_id`, `person_id`, `properties`, `retention_days` (meaningful default of 30), `is_error` (0 = "not an error" is semantically correct)
- **Everything else is Nullable**: all extracted AI properties (trace IDs, model info, tokens, costs, timing, errors, heavy columns)
- **MV uses `JSONExtract(..., 'Nullable(T)')`** for ints/floats to correctly distinguish "0 tokens" from "missing" — unlike `JSONExtractInt` which returns 0 for both
- **Heavy columns use `nullIf(JSONExtractRaw(...), '')`** since JSONExtractRaw preserves raw JSON encoding needed for array/object content
