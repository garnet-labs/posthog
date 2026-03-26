-- v4 RATIOS: behavioral ratios instead of (only) raw counts
-- Hypothesis: engagement depth (ratios) generalizes better than
-- activity volume (raw counts). A light user who is 50% insight-focused
-- may be more likely to create insights than a power user at 5%.
--
-- Keep the v2 winners but add ratio features that normalize for activity level.

SELECT
    person_id,
    countIf(event = 'insight created'
        AND timestamp > now() - interval 14 day) > 0 AS label,

    -- ── Activity level (keep from v2) ────────────────────────────────
    countIf(timestamp <= now() - interval 14 day) AS events_total,
    countIf(timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 14 day) AS events_30d,
    uniqIf(event, timestamp <= now() - interval 14 day) AS unique_event_types,
    dateDiff('day',
        maxIf(timestamp, timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_event,

    -- ── NEW: acceleration (is the user getting more active?) ─────────
    countIf(timestamp > now() - interval 21 day
        AND timestamp <= now() - interval 14 day)
    / greatest(countIf(timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 28 day), 1) AS acceleration_7d_vs_prior,

    -- ── NEW: engagement depth ratios ─────────────────────────────────
    countIf(event = 'insight viewed'
        AND timestamp <= now() - interval 14 day)
    / greatest(countIf(timestamp <= now() - interval 14 day), 1) AS insight_view_ratio,

    countIf(event = 'viewed dashboard'
        AND timestamp <= now() - interval 14 day)
    / greatest(countIf(timestamp <= now() - interval 14 day), 1) AS dashboard_view_ratio,

    countIf(event = 'insight analyzed'
        AND timestamp <= now() - interval 14 day)
    / greatest(countIf(event = 'insight viewed'
        AND timestamp <= now() - interval 14 day), 1) AS analyze_to_view_ratio,

    -- ── Keep raw engagement counts too (for comparison) ──────────────
    countIf(event = 'insight viewed'
        AND timestamp <= now() - interval 14 day) AS insight_viewed,
    countIf(event = 'viewed dashboard'
        AND timestamp <= now() - interval 14 day) AS dashboard_viewed,
    countIf(event = 'insight analyzed'
        AND timestamp <= now() - interval 14 day) AS insight_analyzed

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING events_total >= 5
LIMIT 50000
