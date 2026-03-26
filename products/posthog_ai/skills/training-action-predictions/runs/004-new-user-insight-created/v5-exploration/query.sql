-- v5 EXPLORATION: v2-ablation core + data exploration + AI usage + SDK setup
-- Hypothesis: new users who actively explore their data model (search events,
-- hover definitions, browse event definitions page) and use AI tools are
-- showing "learning intent" that predicts they'll create insights.
-- These are upstream of creating insights but NOT part of the same action.

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

    -- ── NEW: data exploration (learning the product) ─────────────────
    -- Searching for events/properties (2.6x activation rate)
    countIf(e.event = 'taxonomic_filter_search_query'
        AND e.timestamp <= now() - interval 14 day) AS taxonomic_searches,
    -- Hovering event/property definitions (2.3x activation rate)
    countIf(e.event = 'definition hovered'
        AND e.timestamp <= now() - interval 14 day) AS definitions_hovered,
    -- Browsing the event definitions page (3x activation rate)
    countIf(e.event = 'event definitions page load succeeded'
        AND e.timestamp <= now() - interval 14 day) > 0 AS visited_event_definitions,

    -- ── NEW: AI/Max usage (learning via AI) ──────────────────────────
    countIf(e.event = 'ai tool executed'
        AND e.timestamp <= now() - interval 14 day) AS ai_tool_used,
    countIf(e.event = 'ai mode executed'
        AND e.timestamp <= now() - interval 14 day) AS ai_mode_used,

    -- ── NEW: SDK setup journey ───────────────────────────────────────
    countIf(e.event = 'sdk doctor loaded'
        AND e.timestamp <= now() - interval 14 day) > 0 AS used_sdk_doctor,
    countIf(e.event = 'first team event ingested'
        AND e.timestamp <= now() - interval 14 day) > 0 AS has_data_flowing,

    -- ── v2/v4 features that helped ───────────────────────────────────
    uniqIf(toDate(e.timestamp), e.timestamp <= now() - interval 14 day) AS active_days,
    countIf(e.event = '$pageview'
        AND e.properties.$device_type = 'Mobile'
        AND e.timestamp <= now() - interval 14 day) > 0 AS has_mobile_pageview

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
