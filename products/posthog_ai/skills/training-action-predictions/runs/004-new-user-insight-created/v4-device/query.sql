-- v4 DEVICE: v1 behavioral + device/platform metadata from pageview events
-- Hypothesis: mobile users activate at 2x desktop rate (15.9% vs 7.8%).
-- Device type and OS are strong metadata signals available from day 0.
-- Extracted from $pageview event properties (not person properties, which
-- are null for server-side signup events).

SELECT
    e.person_id AS person_id,

    -- ── Label ────────────────────────────────────────────────────────
    countIf(e.event = 'insight created'
        AND e.timestamp > now() - interval 14 day) > 0 AS label,

    -- ── Core activity (v1 strong signals) ────────────────────────────
    countIf(e.timestamp <= now() - interval 14 day) AS events_total,
    countIf(e.timestamp > now() - interval 21 day
        AND e.timestamp <= now() - interval 14 day) AS events_7d,
    uniqIf(e.event, e.timestamp <= now() - interval 14 day) AS unique_event_types,
    dateDiff('day',
        maxIf(e.timestamp, e.timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_event,

    -- ── Engagement depth (v1 strong signals) ─────────────────────────
    countIf(e.event = 'insight viewed'
        AND e.timestamp <= now() - interval 14 day) AS insight_viewed,
    countIf(e.event = 'viewed dashboard'
        AND e.timestamp <= now() - interval 14 day) AS dashboard_viewed,
    countIf(e.event = 'insight analyzed'
        AND e.timestamp <= now() - interval 14 day) AS insight_analyzed,

    -- ── NEW: device/platform from pageview events ────────────────────
    -- Mobile vs desktop (2x activation difference in EDA)
    countIf(e.event = '$pageview'
        AND e.properties.$device_type = 'Mobile'
        AND e.timestamp <= now() - interval 14 day) > 0 AS has_mobile_pageview,
    -- Multi-device usage (checked on both mobile and desktop)
    (countIf(e.event = '$pageview' AND e.properties.$device_type = 'Mobile'
        AND e.timestamp <= now() - interval 14 day) > 0
     AND countIf(e.event = '$pageview' AND e.properties.$device_type = 'Desktop'
        AND e.timestamp <= now() - interval 14 day) > 0) AS is_multi_device,
    -- OS signals
    countIf(e.event = '$pageview'
        AND e.properties.$os IN ('iOS', 'Android')
        AND e.timestamp <= now() - interval 14 day) > 0 AS has_mobile_os,
    -- Mac vs Windows (Mac 8.8% vs Windows 6.6% activation)
    countIf(e.event = '$pageview'
        AND e.properties.$os = 'Mac OS X'
        AND e.timestamp <= now() - interval 14 day) > 0 AS is_mac_user,

    -- ── Activation milestones (from v1) ──────────────────────────────
    countIf(e.event = 'onboarding completed'
        AND e.timestamp <= now() - interval 14 day) > 0 AS completed_onboarding,
    countIf(e.event = 'first team event ingested'
        AND e.timestamp <= now() - interval 14 day) > 0 AS has_data_flowing,
    countIf(e.event = 'user logged in'
        AND e.timestamp <= now() - interval 14 day) AS login_count,

    -- ── v2 velocity that helped (without leaky feature) ──────────────
    uniqIf(toDate(e.timestamp), e.timestamp <= now() - interval 14 day) AS active_days

FROM events e
INNER JOIN (
    SELECT DISTINCT person_id
    FROM events
    WHERE event = 'user signed up'
      AND timestamp >= now() - interval 28 day
      AND timestamp <= now() - interval 14 day
      AND person_id IS NOT NULL
) new_users ON e.person_id = new_users.person_id
WHERE e.person_id IS NOT NULL
  AND e.timestamp >= now() - interval 28 day
  AND e.timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY e.person_id
HAVING events_total >= 2
ORDER BY label DESC, rand()
LIMIT 15000
