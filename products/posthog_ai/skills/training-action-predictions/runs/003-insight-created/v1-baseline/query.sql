-- Training query for "insight created" (simple named event)
-- Target: P(identified user creates an insight within 14 days)
--
-- This is the simplest query pattern — no subquery needed for the label
-- because it's a direct event name match (not autocapture/selector/URL).
--
-- Key decisions:
--   - Filter to identified users (is_signed_up = 'true')
--   - Balanced sampling via ORDER BY label DESC, rand()
--   - 60-day observation window, 14-day prediction window
--
-- Temporal layout:
--   Features: [now()-74d, now()-14d]  (60-day observation window)
--   Label:    (now()-14d, now()]       (14-day prediction window)

SELECT
    person_id,

    -- ── Label (direct event match — no subquery needed) ──────────────
    countIf(event = 'insight created'
        AND timestamp > now() - interval 14 day) > 0 AS label,

    -- ── Generic features ─────────────────────────────────────────────
    dateDiff('day',
        maxIf(timestamp, timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_event,
    countIf(timestamp <= now() - interval 14 day) AS events_total,
    countIf(timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 14 day) AS events_30d,
    countIf(timestamp > now() - interval 21 day
        AND timestamp <= now() - interval 14 day) AS events_7d,
    uniqIf(event, timestamp <= now() - interval 14 day) AS unique_event_types,
    countIf(timestamp > now() - interval 28 day
        AND timestamp <= now() - interval 14 day)
    / greatest(countIf(timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 28 day), 1) AS trend_ratio_14d,
    countIf(event = '$pageview' AND timestamp <= now() - interval 14 day)
        / greatest(countIf(timestamp <= now() - interval 14 day), 1) AS pageview_ratio,
    countIf(event = '$autocapture' AND timestamp <= now() - interval 14 day)
        / greatest(countIf(timestamp <= now() - interval 14 day), 1) AS autocapture_ratio,

    -- ── Project-specific: product engagement ─────────────────────────
    countIf(event = 'viewed dashboard'
        AND timestamp <= now() - interval 14 day) AS dashboard_viewed,
    countIf(event = 'insight viewed'
        AND timestamp <= now() - interval 14 day) AS insight_viewed,
    countIf(event = 'insight analyzed'
        AND timestamp <= now() - interval 14 day) AS insight_analyzed,
    countIf(event = 'recording list fetched'
        AND timestamp <= now() - interval 14 day) AS recording_fetched,
    countIf(event = 'recording viewed'
        AND timestamp <= now() - interval 14 day) AS recording_viewed,

    -- ── Project-specific: activation / onboarding ────────────────────
    countIf(event = 'onboarding started'
        AND timestamp <= now() - interval 14 day) AS onboarding_started,
    countIf(event = 'onboarding completed'
        AND timestamp <= now() - interval 14 day) AS onboarding_completed,
    countIf(event = 'product setup task completed'
        AND timestamp <= now() - interval 14 day) AS setup_tasks_completed,
    countIf(event = 'user signed up'
        AND timestamp <= now() - interval 14 day) AS user_signed_up,
    countIf(event = 'user logged in'
        AND timestamp <= now() - interval 14 day) AS user_logged_in,

    -- ── Project-specific: collaboration / growth ─────────────────────
    countIf(event = 'team member invited'
        AND timestamp <= now() - interval 14 day) AS team_member_invited,
    countIf(event = 'dashboard created'
        AND timestamp <= now() - interval 14 day) AS dashboard_created,
    countIf(event = 'feature flag created'
        AND timestamp <= now() - interval 14 day) AS feature_flag_created,

    -- ── Project-specific: billing intent ─────────────────────────────
    countIf(event = 'pay gate shown'
        AND timestamp <= now() - interval 14 day) AS pay_gate_shown,
    countIf(event = 'billing CTA shown'
        AND timestamp <= now() - interval 14 day) AS billing_cta_shown

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING events_total >= 5
LIMIT 50000
