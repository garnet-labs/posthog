# Baseline feature extraction query

This HogQL query produces a feature matrix for training. It enforces **temporal correctness** — all features are computed from the observation window `[T-90d, T]`, and the label comes from the label window `(T, T+W]`.

Set `T = now() - interval {W} day` so that labels are fully observed at query time.

Replace `{target}` with the target event name (from `ActionPredictionConfig.event_name`) and `{W}` with the lookback window (from `ActionPredictionConfig.lookback_days`).

```sql
SELECT
    person_id,

    -- Label: did they perform the target action in (T, T+W]?
    countIf(event = '{target}'
        AND timestamp > toDateTime('{T}')
        AND timestamp <= toDateTime('{T}') + interval {W} day
    ) > 0 AS label,

    -- Recency
    dateDiff('day',
        maxIf(timestamp, timestamp <= toDateTime('{T}')),
        toDateTime('{T}')
    ) AS days_since_last_event,

    dateDiff('day',
        maxIf(timestamp, event = '{target}' AND timestamp <= toDateTime('{T}')),
        toDateTime('{T}')
    ) AS days_since_last_target,

    -- Frequency (multiple windows)
    countIf(timestamp <= toDateTime('{T}')) AS events_total_90d,
    countIf(timestamp > toDateTime('{T}') - interval 30 day
        AND timestamp <= toDateTime('{T}')) AS events_30d,
    countIf(timestamp > toDateTime('{T}') - interval 7 day
        AND timestamp <= toDateTime('{T}')) AS events_7d,

    -- Target history (excluding label window)
    countIf(event = '{target}'
        AND timestamp <= toDateTime('{T}')) AS target_action_count,

    -- Session behavior
    uniqIf(properties.$session_id,
        timestamp <= toDateTime('{T}')) AS unique_sessions,

    -- Event diversity
    uniqIf(event, timestamp <= toDateTime('{T}')) AS unique_event_types,

    -- Trend: last 15d vs prior 15d
    countIf(timestamp > toDateTime('{T}') - interval 15 day
        AND timestamp <= toDateTime('{T}'))
    / greatest(
        countIf(timestamp > toDateTime('{T}') - interval 30 day
            AND timestamp <= toDateTime('{T}') - interval 15 day),
        1
    ) AS trend_ratio_15d,

    -- Common event ratios
    countIf(event = '$pageview' AND timestamp <= toDateTime('{T}'))
        / greatest(countIf(timestamp <= toDateTime('{T}')), 1) AS pageview_ratio,
    countIf(event = '$autocapture' AND timestamp <= toDateTime('{T}'))
        / greatest(countIf(timestamp <= toDateTime('{T}')), 1) AS autocapture_ratio

FROM events
WHERE team_id = currentTeamId()
  AND person_id IS NOT NULL
  AND timestamp >= toDateTime('{T}') - interval 90 day
  AND timestamp <= toDateTime('{T}') + interval {W} day
GROUP BY person_id
HAVING events_total_90d >= 5
```

## Key constraints

- **No leakage**: the target event is only used in the `label` column and `days_since_last_target` / `target_action_count` (both capped at `T`). Never include target event counts from the label window as features.
- **Minimum activity**: `HAVING events_total_90d >= 5` filters out inactive users who add noise.
- **`greatest(..., 1)`**: prevents division by zero in ratio features.

## Extending this query

When iterating across experiments, add features by extending the `SELECT` clause. Good candidates:

1. **Per-event ratios** for top events: `countIf(event = '{evt}' AND timestamp <= toDateTime('{T}')) / greatest(events_total_90d, 1) AS {evt}_ratio`
2. **Session features**: join against `sessions` table for avg duration, pageviews per session
3. **Person properties**: `person.properties.{prop}` for plan type, signup source, etc.
4. **Day-of-week patterns**: `countIf(toDayOfWeek(timestamp) IN (6, 7) AND timestamp <= toDateTime('{T}')) / greatest(events_total_90d, 1) AS weekend_ratio`
