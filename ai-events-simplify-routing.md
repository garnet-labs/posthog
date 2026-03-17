# ai_events: Simplify single-trace routing to try/fallback

## What to change

Replace the current flag-gated, TTL-checked routing in single-trace runners with a simpler strategy: **always try `ai_events` first, fall back to `events` if no results**.

The feature flag becomes a kill switch (skip the `ai_events` attempt entirely) rather than a rollout gate.

## Why

### The TTL check adds complexity for no real benefit

`is_within_ai_events_ttl` exists to avoid querying `ai_events` for data older than 30 days. But:

- ~99% of usage accesses recent traces, so the check almost always passes
- Querying `ai_events` for old data returns zero rows instantly (indexed by `trace_id`) — same cost as the datetime comparison
- The TTL logic has its own edge cases (1-day buffer for midnight truncation, naive/aware datetime stripping)

### The feature flag shouldn't gate normal operation

Currently, teams only get `ai_events` reads after the flag is enabled. But `ai_events` is populated automatically by the write-side MV — once deployed, new data is there regardless of the flag. The flag forces manual coordination between deployment and rollout.

With try/fallback, new traces automatically get the fast path. The flag remains useful only as an emergency kill switch.

## Plan

### Step 1: Introduce a shared fallback helper

Create a helper that encapsulates the try/fallback pattern, roughly:

```python
def execute_with_ai_events_fallback(
    ai_events_query, events_query, team, ...
) -> QueryResult:
    if not is_ai_events_enabled(team):  # kill switch only
        return execute(events_query)
    result = execute(ai_events_query)
    if result.results:
        return result
    return execute(events_query)
```

All four single-trace consumers call this instead of implementing their own `if/else` routing.

### Step 2: Remove `is_within_ai_events_ttl` and all TTL checking

- Delete `is_within_ai_events_ttl()` from `ai_table_resolver.py`
- Delete its tests from `test_ai_table_resolver.py`
- Remove `AI_EVENTS_TTL_DAYS` constant
- Remove `_should_use_ai_events_table()` methods from `TraceQueryRunner` and `TraceNeighborsQueryRunner`

### Step 3: Simplify `ai_table_resolver.py`

With no TTL check and just the kill switch, the module becomes a single function. Either inline `is_ai_events_enabled()` where it's used or keep it as a thin utility — it no longer needs its own module.

### Step 4: Write queries natively against `ai_events`

Currently, runners write queries against `ai_events` with native columns, then the reverse rewriter (`AiColumnRewriter`) rewrites them back to `properties.$ai_*` for the `events` fallback path. The forward rewriter (`AiPropertyRewriter`) exists for the opposite direction.

With try/fallback, each runner needs two query forms. The simplest approach:

- Write the primary query against `ai_events` natively (no rewriter needed)
- Use `AiColumnRewriter` only for the fallback query
- `AiPropertyRewriter` becomes unused and can be deleted

### Step 5: Inline `TraceMapperMixin`

After the list view routing removal, `TraceMapperMixin` has a single consumer (`TraceQueryRunner`). Inline its methods directly into the runner and delete the mixin from `utils.py`.

### Step 6: Remove the frontend feature flag constant

`LLM_ANALYTICS_AI_EVENTS_TABLE_ROLLOUT` in `constants.tsx` is no longer referenced by any frontend code. Remove it. The backend kill switch reads the flag server-side via `posthoganalytics.feature_enabled`.

## Net result

| Before                                  | After                                               |
| --------------------------------------- | --------------------------------------------------- |
| Flag gates all reads                    | Flag is emergency kill switch only                  |
| TTL check on every request              | No TTL check — indexed empty-result is equally fast |
| 4 runners each with `if/else` routing   | 1 shared helper, 4 call sites                       |
| 2 AST rewriter classes                  | 1 rewriter (reverse only, for fallback)             |
| `ai_table_resolver.py` with 3 functions | 1 function (or inlined)                             |
| `TraceMapperMixin` shared by 2 runners  | Inlined into single consumer                        |
