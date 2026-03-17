# Error Tracking Cache Warming — Implementation Plan

## Goal

Add a Dagster-based cache warming job for error tracking queries,
mirroring the existing web analytics cache warming pattern
in `products/web_analytics/dags/cache_warming.py`.

## Context

- Web analytics already has hourly Dagster cache warming that mines `metrics_query_log_mv`
  for frequently-run queries and re-executes stale ones.
- Error tracking has 4 query runners but no cache warming:
  - `ErrorTrackingQuery`
  - `ErrorTrackingBreakdownsQuery`
  - `ErrorTrackingIssueCorrelationQuery`
  - `ErrorTrackingSimilarIssuesQuery`
- The `TEAM_ERROR_TRACKING` job owner already exists in `posthog/dags/common/owners.py`.
- The error tracking dags directory exists at `products/error_tracking/dags/` (currently only has `symbol_set_cleanup.py`).

## Files to Create / Modify

### 1. `products/error_tracking/dags/cache_warming.py` (new)

Create a new Dagster job following the exact pattern of `products/web_analytics/dags/cache_warming.py`.

**Prometheus metrics:**

```python
STALE_ERROR_TRACKING_QUERIES_GAUGE = Gauge(
    "posthog_cache_warming_stale_error_tracking_query_gauge",
    "Number of stale error tracking queries present",
    ["team_id"],
)
ERROR_TRACKING_QUERIES_COUNTER = Counter(
    "posthog_cache_warming_error_tracking_queries",
    "Number of error tracking queries warmed",
    ["team_id", "normalized_query_hash", "is_cached"],
)
```

**`queries_to_keep_fresh` function:**

- Query `metrics_query_log_mv` filtered to error tracking query types:

  ```sql
  AND query_type IN (
      'ErrorTrackingQuery',
      'ErrorTrackingBreakdownsQuery',
      'ErrorTrackingIssueCorrelationQuery'
  )
  ```

- Note: Exclude `ErrorTrackingSimilarIssuesQuery` — it's a specialized search query
  unlikely to benefit from warming.
- Use instance settings for `days` lookback and `minimum_query_count` threshold
  (new settings, see below).

**Dagster ops (3 ops, same pattern as web analytics):**

1. `get_teams_for_error_tracking_warming_op` — reads from `ERROR_TRACKING_WARMING_TEAMS_TO_WARM` instance setting.
2. `get_error_tracking_queries_for_teams_op` — calls `queries_to_keep_fresh` for each team,
   sets gauge metric.
3. `warm_error_tracking_queries_op` — for each query:
   - Build the query runner via `get_query_runner(query_json, team, limit_context=LimitContext.QUERY_ASYNC)`
   - Check if cached data exists and is fresh via `DjangoCacheQueryCacheManager`
   - If stale or missing, tag with `trigger="errorTrackingQueryWarming"` and `feature=Feature.CACHE_WARMUP`, then `runner.run()`
   - Retry policy: 3 retries, exponential backoff with jitter (same as web analytics)

**Dagster job & schedule:**

```python
@dagster.job(
    description="Warms error tracking query cache for frequently-run queries",
    tags={
        "owner": JobOwners.TEAM_ERROR_TRACKING.value,
        "dagster/error_tracking_cache_warming": "error_tracking_cache_warming",
    },
)
def error_tracking_cache_warming_job():
    team_ids = get_teams_for_error_tracking_warming_op()
    queries = get_error_tracking_queries_for_teams_op(team_ids)
    warm_error_tracking_queries_op(queries)

@dagster.schedule(
    cron_schedule="0 * * * *",  # hourly
    job=error_tracking_cache_warming_job,
    execution_timezone="UTC",
    tags={"owner": JobOwners.TEAM_ERROR_TRACKING.value},
)
def error_tracking_cache_warming_schedule(context):
    skip_reason = check_for_concurrent_runs(context)
    if skip_reason:
        return skip_reason
    return dagster.RunRequest()
```

### 2. `posthog/settings/dynamic_settings.py` (modify)

Add three new instance settings after the existing `WEB_ANALYTICS_WARMING_*` settings:

```python
"ERROR_TRACKING_WARMING_DAYS": (
    get_from_env("ERROR_TRACKING_WARMING_DAYS", default=7, type_cast=int),
    "Number of days to look back for frequently-run error tracking queries",
    int,
),
"ERROR_TRACKING_WARMING_MIN_QUERY_COUNT": (
    get_from_env("ERROR_TRACKING_WARMING_MIN_QUERY_COUNT", default=10, type_cast=int),
    "Minimum query count threshold for error tracking cache warming",
    int,
),
"ERROR_TRACKING_WARMING_TEAMS_TO_WARM": (
    get_from_env("ERROR_TRACKING_WARMING_TEAMS_TO_WARM", default=[], type_cast=list[int]),
    "Teams that will have error tracking cache warming enabled",
    list[int],
),
```

Also add `ERROR_TRACKING_WARMING_DAYS` and `ERROR_TRACKING_WARMING_MIN_QUERY_COUNT`
to the `SETTINGS_ALLOWING_API_OVERRIDE` tuple.

### 3. `posthog/dags/locations/error_tracking.py` (modify)

Register the new job and schedule in the Dagster definitions file.
This is where Dagster discovers jobs/schedules for the error tracking product.

Current file registers `symbol_set_cleanup` assets, jobs, and schedules.
Add the cache warming job and schedule:

```python
import dagster

from products.error_tracking.dags import cache_warming, symbol_set_cleanup

from . import resources

defs = dagster.Definitions(
    assets=[
        symbol_set_cleanup.symbol_sets_to_delete,
        symbol_set_cleanup.symbol_set_cleanup_results,
    ],
    jobs=[
        symbol_set_cleanup.symbol_set_cleanup_job,
        cache_warming.error_tracking_cache_warming_job,
    ],
    schedules=[
        symbol_set_cleanup.daily_symbol_set_cleanup_schedule,
        cache_warming.error_tracking_cache_warming_schedule,
    ],
    resources=resources,
)
```

### 4. `products/error_tracking/dags/__init__.py` (no change needed)

The `__init__.py` is empty — Dagster discovery happens via
`posthog/dags/locations/error_tracking.py` (see above).

### 5. Tests: `products/error_tracking/dags/tests/test_cache_warming.py` (new)

Write tests mirroring the structure of the web analytics cache warming.
Key test cases:

- `test_queries_to_keep_fresh` — mock `sync_execute`, verify correct SQL query types are filtered
- `test_warm_queries_op_skips_cached` — verify fresh cached queries are skipped
- `test_warm_queries_op_warms_stale` — verify stale queries get re-executed
- `test_warm_queries_op_handles_missing_team` — verify graceful handling of deleted teams
- `test_schedule_skips_concurrent_runs` — verify `check_for_concurrent_runs` integration

## Import Note

The `check_for_concurrent_runs` utility lives in `products/web_analytics/dags/web_preaggregated_utils.py`.
Since this is used by error tracking too, consider either:

- (Preferred short-term) Import it from web analytics as-is — it's generic enough.
- (Future) Move it to `posthog/dags/common/utils.py` as shared infra.

## Rollout

1. Deploy with `ERROR_TRACKING_WARMING_TEAMS_TO_WARM` defaulting to `[]` (no teams).
2. Enable for internal team first via instance setting.
3. Monitor Prometheus metrics (`posthog_cache_warming_stale_error_tracking_query_gauge`,
   `posthog_cache_warming_error_tracking_queries`) to verify behavior.
4. Gradually expand to more teams.
