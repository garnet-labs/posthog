-- Training query for "went inactive" (virtual/constructed label)
-- Target: P(active user has zero UI events in the next 14 days)
--
-- This is NOT a single event — the label is the ABSENCE of $pageview/$autocapture.
-- First time we're predicting a non-event. Tests whether the framework
-- handles constructed labels.
--
-- Population: identified users with ≥100 $pageview/$autocapture in the
-- observation window. These are genuinely active UI users.
-- Base rate: ~39% (naturally balanced — no ORDER BY trick needed)
--
-- Temporal layout:
--   Features: [now()-74d, now()-14d]  (60-day observation window)
--   Label:    (now()-14d, now()]       (14-day churn window)

SELECT
    person_id,

    -- ── Label: zero UI events in label window = went inactive ────────
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 14 day) = 0 AS label,

    -- ── UI activity volume ───────────────────────────────────────────
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp <= now() - interval 14 day) AS ui_events_total,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 14 day) AS ui_events_30d,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 21 day
        AND timestamp <= now() - interval 14 day) AS ui_events_7d,

    -- ── Activity trend (declining activity = churn signal) ───────────
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 21 day
        AND timestamp <= now() - interval 14 day)
    / greatest(countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 28 day
        AND timestamp <= now() - interval 21 day), 1) AS ui_trend_week_over_week,

    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 28 day
        AND timestamp <= now() - interval 14 day)
    / greatest(countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 28 day), 1) AS ui_trend_14d,

    -- ── Recency and consistency ──────────────────────────────────────
    dateDiff('day',
        maxIf(timestamp, event IN ('$pageview', '$autocapture')
            AND timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_ui_event,
    uniqIf(toDate(timestamp),
        event IN ('$pageview', '$autocapture')
        AND timestamp <= now() - interval 14 day) AS active_days,

    -- ── General activity ─────────────────────────────────────────────
    countIf(timestamp <= now() - interval 14 day) AS events_total,
    uniqIf(event, timestamp <= now() - interval 14 day) AS unique_event_types,

    -- ── Product engagement depth ─────────────────────────────────────
    countIf(event = 'insight viewed'
        AND timestamp <= now() - interval 14 day) AS insight_viewed,
    countIf(event = 'insight created'
        AND timestamp <= now() - interval 14 day) AS insight_created,
    countIf(event = 'viewed dashboard'
        AND timestamp <= now() - interval 14 day) AS dashboard_viewed,
    countIf(event = 'recording viewed'
        AND timestamp <= now() - interval 14 day) AS recording_viewed,

    -- ── Collaboration signals (invested users churn less?) ───────────
    countIf(event = 'team member invited'
        AND timestamp <= now() - interval 14 day) AS team_member_invited,
    countIf(event = 'dashboard created'
        AND timestamp <= now() - interval 14 day) AS dashboard_created,

    -- ── Billing / value signals ──────────────────────────────────────
    countIf(event = 'billing subscription paid'
        AND timestamp <= now() - interval 14 day) AS billing_paid,
    countIf(event = 'pay gate shown'
        AND timestamp <= now() - interval 14 day) AS pay_gate_shown,

    -- ── Login frequency ──────────────────────────────────────────────
    countIf(event = 'user logged in'
        AND timestamp <= now() - interval 14 day) AS login_count

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING ui_events_total >= 100
LIMIT 50000
