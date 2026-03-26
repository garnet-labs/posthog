-- v2 SIMPLE: only the 8 features with importance > 0.03
-- Hypothesis: dropping 15 weak features reduces noise without losing AUC

SELECT
    person_id,
    countIf(event = 'insight created'
        AND timestamp > now() - interval 14 day) > 0 AS label,

    -- Top generic
    countIf(timestamp <= now() - interval 14 day) AS events_total,
    countIf(timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 14 day) AS events_30d,
    countIf(timestamp > now() - interval 21 day
        AND timestamp <= now() - interval 14 day) AS events_7d,
    uniqIf(event, timestamp <= now() - interval 14 day) AS unique_event_types,
    dateDiff('day',
        maxIf(timestamp, timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_event,

    -- Top product engagement
    countIf(event = 'insight analyzed'
        AND timestamp <= now() - interval 14 day) AS insight_analyzed,
    countIf(event = 'viewed dashboard'
        AND timestamp <= now() - interval 14 day) AS dashboard_viewed,
    countIf(event = 'insight viewed'
        AND timestamp <= now() - interval 14 day) AS insight_viewed

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING events_total >= 5
LIMIT 50000
