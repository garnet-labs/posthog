-- v6 DAY 3: predict insight creation using ONLY the first 3 days of activity
-- Use case: score new users at day 3 for early onboarding intervention
--
-- KEY DESIGN: per-user time anchoring ("time travel")
-- Each user's features are computed relative to THEIR signup time:
--   Features: [signup_time, signup_time + 3 days]
--   Label:    (signup_time + 3 days, signup_time + 17 days]
--
-- This gives us all signups from the last 45 days as training data
-- (not just a narrow slice), and matches how scoring would work in
-- production: score each user exactly 3 days after they sign up.

SELECT
    e.person_id AS person_id,

    -- ── Label: created insight between day 3 and day 17 ──────────────
    countIf(e.event = 'insight created'
        AND e.timestamp > su.signup_time + interval 3 day
        AND e.timestamp <= su.signup_time + interval 17 day) > 0 AS label,

    -- ── Day 1-3 activity volume ──────────────────────────────────────
    countIf(e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) AS events_total,
    uniqIf(e.event,
        e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) AS unique_event_types,
    uniqIf(toDate(e.timestamp),
        e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) AS active_days,

    -- ── Did they come back after day 1? ──────────────────────────────
    dateDiff('day',
        minIf(e.timestamp, e.timestamp >= su.signup_time),
        maxIf(e.timestamp, e.timestamp <= su.signup_time + interval 3 day)) AS days_span,

    -- ── Engagement depth (first 3 days) ──────────────────────────────
    countIf(e.event = 'insight viewed'
        AND e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) AS insight_viewed,
    countIf(e.event = 'viewed dashboard'
        AND e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) AS dashboard_viewed,
    countIf(e.event = 'insight analyzed'
        AND e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) AS insight_analyzed,

    -- ── Activation milestones (within 3 days) ────────────────────────
    countIf(e.event = 'onboarding completed'
        AND e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) > 0 AS completed_onboarding,
    countIf(e.event = 'first team event ingested'
        AND e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) > 0 AS has_data_flowing,
    countIf(e.event = 'product setup task completed'
        AND e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) AS setup_tasks_completed,
    countIf(e.event = 'user logged in'
        AND e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) AS login_count,

    -- ── Exploration signals (first 3 days) ───────────────────────────
    countIf(e.event = 'taxonomic_filter_search_query'
        AND e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) AS taxonomic_searches,
    countIf(e.event = 'definition hovered'
        AND e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) AS definitions_hovered,

    -- ── Device (from first pageview) ─────────────────────────────────
    countIf(e.event = '$pageview'
        AND e.properties.$device_type = 'Mobile'
        AND e.timestamp >= su.signup_time
        AND e.timestamp <= su.signup_time + interval 3 day) > 0 AS has_mobile_pageview

FROM events e
INNER JOIN (
    -- Get each user's signup time
    SELECT person_id, min(timestamp) AS signup_time
    FROM events
    WHERE event = 'user signed up'
      AND timestamp >= now() - interval 45 day
      AND timestamp <= now() - interval 17 day
      AND person_id IS NOT NULL
    GROUP BY person_id
) su ON e.person_id = su.person_id
WHERE e.person_id IS NOT NULL
  AND e.timestamp >= su.signup_time
  AND e.timestamp <= su.signup_time + interval 17 day
  AND person.properties.is_signed_up = 'true'
GROUP BY e.person_id, su.signup_time
HAVING events_total >= 1
ORDER BY label DESC, rand()
LIMIT 15000
