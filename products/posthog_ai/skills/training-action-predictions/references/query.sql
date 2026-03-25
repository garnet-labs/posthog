-- Feature extraction query for action prediction.
--
-- This is a REFERENCE — the agent adapts it per experiment.
-- The same query structure is used for both training and scoring:
--
--   Training: T = now() - interval {W} day (so labels are fully observed)
--             Includes label column
--             FROM range covers observation + label window
--
--   Scoring:  T = now()
--             No label column
--             FROM range covers observation window only
--
-- The agent stores the final query in artifact_scripts["query"] per run.
--
-- Constraints:
--   - Features must only use data from BEFORE T (no leakage)
--   - Target event excluded from features (only in label + historical counts)
--   - LIMIT 50000 because HogQL defaults to 100
--   - Do NOT use currentTeamId() — MCP scopes automatically

-- ── Training mode example ──────────────────────────────────────────────
-- Target: downloaded_file, Lookback: 28 days, Observation: 90 days

SELECT
    person_id,

    -- Label (training only — remove for scoring)
    countIf(event = 'downloaded_file'
        AND timestamp > now() - interval 28 day
    ) > 0 AS label,

    -- Recency
    dateDiff('day',
        maxIf(timestamp, timestamp <= now() - interval 28 day),
        now() - interval 28 day
    ) AS days_since_last_event,
    dateDiff('day',
        maxIf(timestamp, event = 'downloaded_file' AND timestamp <= now() - interval 28 day),
        now() - interval 28 day
    ) AS days_since_last_target,

    -- Frequency
    countIf(timestamp <= now() - interval 28 day) AS events_total,
    countIf(timestamp > now() - interval 58 day
        AND timestamp <= now() - interval 28 day) AS events_30d,
    countIf(timestamp > now() - interval 35 day
        AND timestamp <= now() - interval 28 day) AS events_7d,

    -- Target history (before label window)
    countIf(event = 'downloaded_file'
        AND timestamp <= now() - interval 28 day) AS target_action_count,

    -- Event diversity
    uniqIf(event, timestamp <= now() - interval 28 day) AS unique_event_types,

    -- Trend: last 15d vs prior 15d
    countIf(timestamp > now() - interval 43 day
        AND timestamp <= now() - interval 28 day)
    / greatest(
        countIf(timestamp > now() - interval 58 day
            AND timestamp <= now() - interval 43 day),
        1
    ) AS trend_ratio_15d,

    -- Event ratios (agent adds more per experiment)
    countIf(event = '$pageview' AND timestamp <= now() - interval 28 day)
        / greatest(countIf(timestamp <= now() - interval 28 day), 1) AS pageview_ratio,
    countIf(event = '$autocapture' AND timestamp <= now() - interval 28 day)
        / greatest(countIf(timestamp <= now() - interval 28 day), 1) AS autocapture_ratio

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 118 day  -- observation (90) + lookback (28)
  AND timestamp <= now()
GROUP BY person_id
HAVING events_total >= 5
LIMIT 50000
