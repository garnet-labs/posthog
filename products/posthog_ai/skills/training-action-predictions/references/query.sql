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
--             No label column (predict.py auto-transforms the training query)
--             FROM range covers observation window only
--
-- ═══════════════════════════════════════════════════════════════════════
-- CRITICAL DECISIONS (make during EDA, before writing this query):
--
-- 1. POPULATION: filter to identified/real users. Find the right signal
--    for this project (email, is_signed_up, is_identified, etc.).
--    Most projects have 80-95% anonymous/bot traffic.
--
-- 2. LABEL TYPE:
--    - Simple event: countIf(event = 'X' AND ...) > 0 AS label
--    - Action (autocapture/selector): use IN subquery (see below)
--    - Constructed (churn): countIf(event IN (...) AND ...) = 0 AS label
--
-- 3. SAMPLING: for rare events (< 3% base rate), add:
--    ORDER BY label DESC, rand()
--    so all positives come first in the LIMIT.
--
-- 4. TIME ANCHORING: for lifecycle predictions, use per-user anchoring
--    instead of fixed T (see pattern at bottom of file).
-- ═══════════════════════════════════════════════════════════════════════

-- ── Simple event label example ───────────────────────────────────────
-- Target: downloaded_file, Lookback: 28 days, Observation: 90 days

SELECT
    person_id,

    -- Label (training only — predict.py strips this automatically)
    countIf(event = 'downloaded_file'
        AND timestamp > now() - interval 28 day
    ) > 0 AS label,

    -- ═══════════════════════════════════════════════════════════════════
    -- GENERIC FEATURES — baseline for any project
    -- ═══════════════════════════════════════════════════════════════════

    -- Recency
    dateDiff('day',
        maxIf(timestamp, timestamp <= now() - interval 28 day),
        now() - interval 28 day
    ) AS days_since_last_event,

    -- Frequency
    countIf(timestamp <= now() - interval 28 day) AS events_total,
    countIf(timestamp > now() - interval 58 day
        AND timestamp <= now() - interval 28 day) AS events_30d,
    countIf(timestamp > now() - interval 35 day
        AND timestamp <= now() - interval 28 day) AS events_7d,

    -- Event diversity
    uniqIf(event, timestamp <= now() - interval 28 day) AS unique_event_types,

    -- Trend: recent vs prior period
    countIf(timestamp > now() - interval 43 day
        AND timestamp <= now() - interval 28 day)
    / greatest(
        countIf(timestamp > now() - interval 58 day
            AND timestamp <= now() - interval 43 day),
        1
    ) AS trend_ratio_15d,

    -- Consistency: how many distinct days active
    uniqIf(toDate(timestamp),
        timestamp <= now() - interval 28 day) AS active_days

    -- ═══════════════════════════════════════════════════════════════════
    -- PROJECT-SPECIFIC FEATURES — discovered during EDA
    -- Start lean. Add only if AUC improves. Behavioral features (what
    -- users DID) consistently beat metadata (who they ARE).
    -- ═══════════════════════════════════════════════════════════════════

    -- Custom event counts:
    -- countIf(event = 'subscription_renewed'
    --     AND timestamp <= now() - interval 28 day) AS subscription_renewals,

    -- Event property features:
    -- countIf(event = '$pageview'
    --     AND properties.$current_url LIKE '%/settings%'
    --     AND timestamp <= now() - interval 28 day) AS settings_page_views,

    -- Person properties (need any() in GROUP BY, 0.0 default):
    -- toFloatOrDefault(toString(any(person.properties.company_size)), 0.0)
    --     AS company_size,

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 118 day  -- observation (90) + lookback (28)
  AND timestamp <= now()
  -- POPULATION FILTER: adapt per project (examples below)
  -- AND person.properties.email IS NOT NULL
  -- AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING events_total >= 5
-- For rare events (< 3% base rate), uncomment:
-- ORDER BY label DESC, rand()
LIMIT 50000

-- ═══════════════════════════════════════════════════════════════════════
-- PATTERN: Action-based label (autocapture + selectors or URL matching)
-- Use IN subquery to isolate expensive LIKE scans to the label window.
-- ═══════════════════════════════════════════════════════════════════════
--
-- if(person_id IN (
--     SELECT DISTINCT person_id
--     FROM events
--     WHERE event = '$autocapture'
--       AND (elements_chain LIKE '%my-button-selector%'
--            OR properties.$current_url LIKE '%/my-page%')
--       AND timestamp > now() - interval 14 day
--       AND timestamp <= now()
--       AND person_id IS NOT NULL
-- ), 1, 0) AS label,

-- ═══════════════════════════════════════════════════════════════════════
-- PATTERN: Constructed churn label (absence of events)
-- ═══════════════════════════════════════════════════════════════════════
--
-- countIf(event IN ('$pageview', '$autocapture')
--     AND timestamp > now() - interval 14 day) = 0 AS label,
-- (with HAVING that ensures activity in observation window)

-- ═══════════════════════════════════════════════════════════════════════
-- PATTERN: Per-user time anchoring (lifecycle/activation predictions)
-- ═══════════════════════════════════════════════════════════════════════
--
-- SELECT
--     e.person_id AS person_id,
--     countIf(e.event = 'target_event'
--         AND e.timestamp > su.anchor + interval 3 day
--         AND e.timestamp <= su.anchor + interval 17 day) > 0 AS label,
--     countIf(e.timestamp >= su.anchor
--         AND e.timestamp <= su.anchor + interval 3 day) AS events_total,
--     ...
-- FROM events e
-- INNER JOIN (
--     SELECT person_id, min(timestamp) AS anchor
--     FROM events
--     WHERE event = 'user signed up'
--       AND timestamp >= now() - interval 45 day
--       AND person_id IS NOT NULL
--     GROUP BY person_id
-- ) su ON e.person_id = su.person_id
-- WHERE ...
-- GROUP BY e.person_id, su.anchor

-- ═══════════════════════════════════════════════════════════════════════
-- PATTERN: Weekly activity decay (churn/retention predictions)
-- ═══════════════════════════════════════════════════════════════════════
--
-- countIf(event IN ('$pageview', '$autocapture')
--     AND timestamp > now() - interval 21 day
--     AND timestamp <= now() - interval 14 day) AS ui_week_1,
-- countIf(...) AS ui_week_2,  -- and so on for 6-8 weeks
-- (recent weeks / earlier weeks) AS recent_vs_earlier_ratio,
-- (count of weeks with any activity) AS weeks_active,
