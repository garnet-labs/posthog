-- v2 VELOCITY ABLATION: same as v2 but WITHOUT days_to_first_insight_view
-- Testing whether the 0.753→0.908 jump is real or driven by one leaky feature

SELECT
    e.person_id AS person_id,
    countIf(e.event = 'insight created'
        AND e.timestamp > now() - interval 14 day) > 0 AS label,

    countIf(e.timestamp <= now() - interval 14 day) AS events_total,
    countIf(e.timestamp > now() - interval 21 day
        AND e.timestamp <= now() - interval 14 day) AS events_7d,
    uniqIf(e.event, e.timestamp <= now() - interval 14 day) AS unique_event_types,
    dateDiff('day',
        maxIf(e.timestamp, e.timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_event,

    countIf(e.event = 'insight viewed'
        AND e.timestamp <= now() - interval 14 day) AS insight_viewed,
    countIf(e.event = 'viewed dashboard'
        AND e.timestamp <= now() - interval 14 day) AS dashboard_viewed,
    countIf(e.event = 'insight analyzed'
        AND e.timestamp <= now() - interval 14 day) AS insight_analyzed,

    -- Velocity features WITHOUT days_to_first_insight_view
    dateDiff('day',
        minIf(e.timestamp, e.event = 'user signed up'),
        minIf(e.timestamp, e.event = 'onboarding completed')) AS days_to_onboarding,
    dateDiff('day',
        minIf(e.timestamp, e.event = 'user signed up'),
        minIf(e.timestamp, e.event = 'first team event ingested')) AS days_to_first_event,

    uniqIf(toDate(e.timestamp), e.timestamp <= now() - interval 14 day) AS active_days,
    countIf(e.event = 'user logged in'
        AND e.timestamp <= now() - interval 14 day) AS login_count,

    (if(countIf(e.event = 'insight viewed' AND e.timestamp <= now() - interval 14 day) > 0, 1, 0)
     + if(countIf(e.event = 'recording list fetched' AND e.timestamp <= now() - interval 14 day) > 0, 1, 0)
     + if(countIf(e.event = 'feature flag created' AND e.timestamp <= now() - interval 14 day) > 0, 1, 0)
     + if(countIf(e.event IN ('$ai_generation', '$ai_trace') AND e.timestamp <= now() - interval 14 day) > 0, 1, 0)
    ) AS products_explored,

    countIf(e.event = 'onboarding completed'
        AND e.timestamp <= now() - interval 14 day) > 0 AS completed_onboarding,
    countIf(e.event = 'first team event ingested'
        AND e.timestamp <= now() - interval 14 day) > 0 AS has_data_flowing

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
