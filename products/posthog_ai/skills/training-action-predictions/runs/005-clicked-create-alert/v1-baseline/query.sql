-- Training query for "Clicked Create Alert" (prod action 253406)
-- Target: P(analytics user clicks "Create alert" within 30 days)
--
-- Population: identified users with ≥50 events who have viewed a dashboard
-- or created an insight in the observation window. These are "analytics users"
-- — the people who could discover alerts but mostly haven't.
--
-- Very rare event (~164 positives in 30 days among 181K analytics users).
-- Stress test for the pipeline on extreme class imbalance.
--
-- Temporal layout:
--   Features: [now()-120d, now()-30d]  (90-day observation window)
--   Label:    (now()-30d, now()]        (30-day prediction window)

SELECT
    person_id,

    -- ── Label (via IN subquery — autocapture + text + URL) ───────────
    if(person_id IN (
        SELECT DISTINCT person_id
        FROM events
        WHERE event = '$autocapture'
          AND elements_chain LIKE '%Create alert%'
          AND properties.$current_url LIKE '%/alerts%'
          AND timestamp > now() - interval 30 day
          AND timestamp <= now()
          AND person_id IS NOT NULL
    ), 1, 0) AS label,

    -- ── Generic activity ─────────────────────────────────────────────
    countIf(timestamp <= now() - interval 30 day) AS events_total,
    countIf(timestamp > now() - interval 60 day
        AND timestamp <= now() - interval 30 day) AS events_30d,
    countIf(timestamp > now() - interval 37 day
        AND timestamp <= now() - interval 30 day) AS events_7d,
    uniqIf(event, timestamp <= now() - interval 30 day) AS unique_event_types,
    dateDiff('day',
        maxIf(timestamp, timestamp <= now() - interval 30 day),
        now() - interval 30 day) AS days_since_last_event,
    uniqIf(toDate(timestamp), timestamp <= now() - interval 30 day) AS active_days,

    -- ── Analytics depth (these users already use analytics) ──────────
    countIf(event = 'insight created'
        AND timestamp <= now() - interval 30 day) AS insights_created,
    countIf(event = 'insight viewed'
        AND timestamp <= now() - interval 30 day) AS insights_viewed,
    countIf(event = 'insight analyzed'
        AND timestamp <= now() - interval 30 day) AS insights_analyzed,
    countIf(event = 'viewed dashboard'
        AND timestamp <= now() - interval 30 day) AS dashboards_viewed,
    countIf(event = 'dashboard created'
        AND timestamp <= now() - interval 30 day) AS dashboards_created,
    countIf(event = 'insight saved'
        AND timestamp <= now() - interval 30 day) AS insights_saved,

    -- ── Alerts-adjacent features (safe — upstream of creating) ───────
    -- Visited the alerts page (browsing, not creating)
    countIf(event = '$pageview'
        AND properties.$current_url LIKE '%/alerts%'
        AND timestamp <= now() - interval 30 day) AS alerts_page_views,
    -- Created or viewed subscriptions (related monitoring feature)
    countIf(event = 'subscription created'
        AND timestamp <= now() - interval 30 day) AS subscriptions_created,

    -- ── Power user signals ───────────────────────────────────────────
    countIf(event = 'feature flag created'
        AND timestamp <= now() - interval 30 day) AS feature_flags_created,
    countIf(event = 'export created'
        AND timestamp <= now() - interval 30 day) AS exports_created,
    countIf(event = 'cohort created'
        AND timestamp <= now() - interval 30 day) AS cohorts_created,
    countIf(event = 'team member invited'
        AND timestamp <= now() - interval 30 day) AS team_members_invited,

    -- ── Trend / recency ──────────────────────────────────────────────
    countIf(timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 30 day)
    / greatest(countIf(timestamp > now() - interval 60 day
        AND timestamp <= now() - interval 44 day), 1) AS trend_ratio

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 120 day
  AND timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING events_total >= 50
  AND (countIf(event = 'insight created' AND timestamp <= now() - interval 30 day) > 0
       OR countIf(event = 'viewed dashboard' AND timestamp <= now() - interval 30 day) > 0)
ORDER BY label DESC, rand()
LIMIT 15000
