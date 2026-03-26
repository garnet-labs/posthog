-- v3 ENRICHED: keep strong features, add person properties + query events
-- Hypothesis: person properties (team size, project count) and query-related
-- events add signal about org maturity and analytics intent

SELECT
    person_id,
    countIf(event = 'insight created'
        AND timestamp > now() - interval 14 day) > 0 AS label,

    -- ── Strong generic features ──────────────────────────────────────
    dateDiff('day',
        maxIf(timestamp, timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_event,
    countIf(timestamp <= now() - interval 14 day) AS events_total,
    countIf(timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 14 day) AS events_30d,
    countIf(timestamp > now() - interval 21 day
        AND timestamp <= now() - interval 14 day) AS events_7d,
    uniqIf(event, timestamp <= now() - interval 14 day) AS unique_event_types,

    -- ── Strong product engagement ────────────────────────────────────
    countIf(event = 'insight analyzed'
        AND timestamp <= now() - interval 14 day) AS insight_analyzed,
    countIf(event = 'viewed dashboard'
        AND timestamp <= now() - interval 14 day) AS dashboard_viewed,
    countIf(event = 'insight viewed'
        AND timestamp <= now() - interval 14 day) AS insight_viewed,
    countIf(event = 'user logged in'
        AND timestamp <= now() - interval 14 day) AS user_logged_in,

    -- ── NEW: query/analytics intent ──────────────────────────────────
    countIf(event = 'query executed'
        AND timestamp <= now() - interval 14 day) AS query_executed,
    countIf(event = 'query completed'
        AND timestamp <= now() - interval 14 day) AS query_completed,
    countIf(event = 'taxonomic_filter_search_query'
        AND timestamp <= now() - interval 14 day) AS taxonomic_search,
    countIf(event = 'definition hovered'
        AND timestamp <= now() - interval 14 day) AS definition_hovered,

    -- ── NEW: person properties (org maturity signals) ────────────────
    -- Must use any() since person properties aren't in GROUP BY
    toFloatOrDefault(toString(any(person.properties.team_member_count_all)), 0.0) AS team_member_count,
    toFloatOrDefault(toString(any(person.properties.project_count)), 0.0) AS project_count,
    toFloatOrDefault(toString(any(person.properties.organization_count)), 0.0) AS organization_count,
    if(any(person.properties.completed_onboarding_once) = 'true', 1.0, 0.0) AS completed_onboarding

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING events_total >= 5
LIMIT 50000
