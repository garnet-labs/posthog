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
--
-- Feature strategy:
--   The query has two tiers of features. Generic features provide a
--   reasonable baseline for any project. Project-specific features —
--   engineered from custom events, event properties, and person
--   properties discovered during EDA — are where the real predictive
--   uplift comes from. The agent should always add project-specific
--   features based on what it learns about the project's data.

-- ── Training mode example ──────────────────────────────────────────────
-- Target: downloaded_file, Lookback: 28 days, Observation: 90 days

SELECT
    person_id,

    -- Label (training only — remove for scoring)
    countIf(event = 'downloaded_file'
        AND timestamp > now() - interval 28 day
    ) > 0 AS label,

    -- ═══════════════════════════════════════════════════════════════════
    -- GENERIC FEATURES — baseline for any project
    -- These use standard PostHog events and general behavioral signals.
    -- They get you to a reasonable AUC but are the same for every project.
    -- ═══════════════════════════════════════════════════════════════════

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

    -- Standard event ratios
    countIf(event = '$pageview' AND timestamp <= now() - interval 28 day)
        / greatest(countIf(timestamp <= now() - interval 28 day), 1) AS pageview_ratio,
    countIf(event = '$autocapture' AND timestamp <= now() - interval 28 day)
        / greatest(countIf(timestamp <= now() - interval 28 day), 1) AS autocapture_ratio

    -- ═══════════════════════════════════════════════════════════════════
    -- PROJECT-SPECIFIC FEATURES — the agent's unique advantage
    -- Discovered during EDA by exploring the project's custom events,
    -- event properties, and person properties. These are what push
    -- AUC from 0.6-0.7 (generic) to 0.8+ (custom).
    --
    -- The agent should add features here based on what it learns about
    -- the specific project. Examples of what to look for:
    --
    -- Custom event counts/ratios:
    --   countIf(event = 'subscription_renewed'
    --       AND timestamp <= now() - interval 28 day) AS subscription_renewals,
    --   countIf(event = 'api_key_created'
    --       AND timestamp <= now() - interval 28 day)
    --       / greatest(events_total, 1) AS api_key_ratio,
    --
    -- Event property features:
    --   countIf(event = '$pageview'
    --       AND properties.$current_url LIKE '%/settings%'
    --       AND timestamp <= now() - interval 28 day) AS settings_page_views,
    --   countIf(event = 'purchase'
    --       AND JSONExtractFloat(properties, 'amount') > 100
    --       AND timestamp <= now() - interval 28 day) AS high_value_purchases,
    --
    -- Person property features:
    --   person.properties.plan AS user_plan,
    --   person.properties.company_size AS company_size,
    --
    -- Domain-specific ratios:
    --   countIf(event = 'support_ticket_created' AND timestamp <= now() - interval 28 day)
    --       / greatest(dateDiff('day', min(timestamp), now() - interval 28 day), 1)
    --       AS support_tickets_per_day,
    -- ═══════════════════════════════════════════════════════════════════

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 118 day  -- observation (90) + lookback (28)
  AND timestamp <= now()
GROUP BY person_id
HAVING events_total >= 5
LIMIT 50000
