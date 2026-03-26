-- v2 SIMPLE: top 5 features from v1
-- Same pattern as run 003 — does dropping weak features help?

SELECT
    person_id,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 14 day) = 0 AS label,

    dateDiff('day',
        maxIf(timestamp, event IN ('$pageview', '$autocapture')
            AND timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_ui_event,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 21 day
        AND timestamp <= now() - interval 14 day) AS ui_events_7d,
    uniqIf(toDate(timestamp),
        event IN ('$pageview', '$autocapture')
        AND timestamp <= now() - interval 14 day) AS active_days,
    countIf(timestamp <= now() - interval 14 day) AS events_total,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 14 day) AS ui_events_30d

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING countIf(event IN ('$pageview', '$autocapture') AND timestamp <= now() - interval 14 day) >= 100
LIMIT 50000
