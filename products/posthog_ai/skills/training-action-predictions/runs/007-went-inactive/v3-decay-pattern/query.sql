-- v3 DECAY PATTERN: weekly activity buckets WITHOUT the trivial recency feature
-- Hypothesis: the SHAPE of activity decline (gradual fade vs sudden drop)
-- predicts churn better than just "when did they last visit?"
--
-- Removes days_since_last_ui_event to force the model to learn from patterns.

SELECT
    person_id,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 14 day) = 0 AS label,

    -- ── Weekly UI activity buckets (most recent first) ───────────────
    -- Week 1 = most recent week of observation window
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 21 day
        AND timestamp <= now() - interval 14 day) AS ui_week_1,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 28 day
        AND timestamp <= now() - interval 21 day) AS ui_week_2,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 35 day
        AND timestamp <= now() - interval 28 day) AS ui_week_3,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 42 day
        AND timestamp <= now() - interval 35 day) AS ui_week_4,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 49 day
        AND timestamp <= now() - interval 42 day) AS ui_week_5,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 56 day
        AND timestamp <= now() - interval 49 day) AS ui_week_6,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 63 day
        AND timestamp <= now() - interval 56 day) AS ui_week_7,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 74 day
        AND timestamp <= now() - interval 63 day) AS ui_week_8,

    -- ── Derived: activity trend ──────────────────────────────────────
    -- Recent vs earlier (declining ratio = churn signal)
    (countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 28 day
        AND timestamp <= now() - interval 14 day))
    / greatest(countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 56 day
        AND timestamp <= now() - interval 28 day), 1) AS recent_vs_earlier_ratio,

    -- ── Consistency ──────────────────────────────────────────────────
    uniqIf(toDate(timestamp),
        event IN ('$pageview', '$autocapture')
        AND timestamp <= now() - interval 14 day) AS active_days,
    -- How many of the 8 weeks had activity?
    (if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 21 day AND timestamp <= now() - interval 14 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 28 day AND timestamp <= now() - interval 21 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 35 day AND timestamp <= now() - interval 28 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 42 day AND timestamp <= now() - interval 35 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 49 day AND timestamp <= now() - interval 42 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 56 day AND timestamp <= now() - interval 49 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 63 day AND timestamp <= now() - interval 56 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 74 day AND timestamp <= now() - interval 63 day) > 0, 1, 0)
    ) AS weeks_active,

    -- ── Overall volume ───────────────────────────────────────────────
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp <= now() - interval 14 day) AS ui_events_total,
    uniqIf(event, timestamp <= now() - interval 14 day) AS unique_event_types

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING ui_events_total >= 100
LIMIT 50000
