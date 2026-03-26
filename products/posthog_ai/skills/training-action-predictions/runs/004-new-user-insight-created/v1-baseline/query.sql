-- Training query: "Will this new user create an insight in their first 14 days?"
-- Population: users who signed up between now-28d and now-14d (≤14 days old at label start)
-- Label: did they create an insight in the following 14 days (now-14d to now)?
-- Features: their early activity in the observation window (up to 14 days of behavior)
--
-- This is an ACTIVATION prediction — targeting new users specifically.
-- Much more actionable than predicting insight creation for all users.
--
-- Base rate: 7.5% (1,984 / 26,363 new users)

SELECT
    e.person_id AS person_id,

    -- ── Label ────────────────────────────────────────────────────────
    countIf(e.event = 'insight created'
        AND e.timestamp > now() - interval 14 day) > 0 AS label,

    -- ── Generic activity features ────────────────────────────────────
    countIf(e.timestamp <= now() - interval 14 day) AS events_total,
    countIf(e.timestamp > now() - interval 21 day
        AND e.timestamp <= now() - interval 14 day) AS events_7d,
    uniqIf(e.event, e.timestamp <= now() - interval 14 day) AS unique_event_types,
    dateDiff('day',
        maxIf(e.timestamp, e.timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_event,

    -- ── Engagement depth (strong signals from run 003) ───────────────
    countIf(e.event = 'insight viewed'
        AND e.timestamp <= now() - interval 14 day) AS insight_viewed,
    countIf(e.event = 'viewed dashboard'
        AND e.timestamp <= now() - interval 14 day) AS dashboard_viewed,
    countIf(e.event = 'insight analyzed'
        AND e.timestamp <= now() - interval 14 day) AS insight_analyzed,

    -- ── New user activation signals ──────────────────────────────────
    countIf(e.event = 'onboarding started'
        AND e.timestamp <= now() - interval 14 day) AS onboarding_started,
    countIf(e.event = 'onboarding completed'
        AND e.timestamp <= now() - interval 14 day) AS onboarding_completed,
    countIf(e.event = 'product setup task completed'
        AND e.timestamp <= now() - interval 14 day) AS setup_tasks_completed,
    countIf(e.event = 'onboarding step completed'
        AND e.timestamp <= now() - interval 14 day) AS onboarding_steps_completed,
    countIf(e.event = 'onboarding_products_confirmed'
        AND e.timestamp <= now() - interval 14 day) AS products_confirmed,

    -- ── Early product exploration ────────────────────────────────────
    countIf(e.event = 'recording list fetched'
        AND e.timestamp <= now() - interval 14 day) AS recording_fetched,
    countIf(e.event = 'user logged in'
        AND e.timestamp <= now() - interval 14 day) AS user_logged_in,
    countIf(e.event = 'team member invited'
        AND e.timestamp <= now() - interval 14 day) AS team_member_invited,
    countIf(e.event = 'first team event ingested'
        AND e.timestamp <= now() - interval 14 day) AS first_event_ingested

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
