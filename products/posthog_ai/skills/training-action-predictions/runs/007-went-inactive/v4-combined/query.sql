-- v4 COMBINED: v3 decay pattern + the dominant recency feature back in
-- Hypothesis: days_since_last_ui_event is legitimately the strongest signal
-- and the decay pattern features add complementary information on top.
-- Best of both worlds.

SELECT
    person_id,
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 14 day) = 0 AS label,

    -- ── The dominant recency signal (back from v1) ───────────────────
    dateDiff('day',
        maxIf(timestamp, event IN ('$pageview', '$autocapture')
            AND timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_ui_event,

    -- ── Weekly activity buckets (from v3) ────────────────────────────
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

    -- ── Decay signals (from v3) ──────────────────────────────────────
    (countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 28 day
        AND timestamp <= now() - interval 14 day))
    / greatest(countIf(event IN ('$pageview', '$autocapture')
        AND timestamp > now() - interval 56 day
        AND timestamp <= now() - interval 28 day), 1) AS recent_vs_earlier_ratio,

    -- ── Consistency (from v3) ────────────────────────────────────────
    uniqIf(toDate(timestamp),
        event IN ('$pageview', '$autocapture')
        AND timestamp <= now() - interval 14 day) AS active_days,
    (if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 21 day AND timestamp <= now() - interval 14 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 28 day AND timestamp <= now() - interval 21 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 35 day AND timestamp <= now() - interval 28 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 42 day AND timestamp <= now() - interval 35 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 49 day AND timestamp <= now() - interval 42 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 56 day AND timestamp <= now() - interval 49 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 63 day AND timestamp <= now() - interval 56 day) > 0, 1, 0)
     + if(countIf(event IN ('$pageview', '$autocapture') AND timestamp > now() - interval 74 day AND timestamp <= now() - interval 63 day) > 0, 1, 0)
    ) AS weeks_active,

    -- ── Total volume ─────────────────────────────────────────────────
    countIf(event IN ('$pageview', '$autocapture')
        AND timestamp <= now() - interval 14 day) AS ui_events_total

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING ui_events_total >= 100
LIMIT 50000
