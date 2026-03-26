-- v3 CONTEXT: v1 behavioral features + acquisition/onboarding context
-- Hypothesis: what the user chose during onboarding (product selection)
-- and how they signed up (region, method) adds signal that pure behavioral
-- features can't capture — especially for users with very little activity.

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

    -- ── NEW: product onboarding selection ────────────────────────────
    -- Which products did they onboard into? (declared intent)
    countIf(e.event = 'product onboarding completed'
        AND e.properties.product_key = 'product_analytics'
        AND e.timestamp <= now() - interval 14 day) > 0 AS onboarded_product_analytics,
    countIf(e.event = 'product onboarding completed'
        AND e.properties.product_key = 'session_replay'
        AND e.timestamp <= now() - interval 14 day) > 0 AS onboarded_session_replay,
    countIf(e.event = 'product onboarding completed'
        AND e.properties.product_key = 'web_analytics'
        AND e.timestamp <= now() - interval 14 day) > 0 AS onboarded_web_analytics,
    countIf(e.event = 'product onboarding completed'
        AND e.properties.product_key = 'feature_flags'
        AND e.timestamp <= now() - interval 14 day) > 0 AS onboarded_feature_flags,
    -- Total products onboarded (breadth of interest)
    uniqIf(e.properties.product_key,
        e.event = 'product onboarding completed'
        AND e.timestamp <= now() - interval 14 day) AS products_onboarded_count,

    -- ── NEW: signup context ──────────────────────────────────────────
    -- Region (EU users activate slightly more)
    if(any(person.properties.$initial_current_url) LIKE '%eu.posthog%', 1.0, 0.0) AS is_eu_signup,
    -- Social vs regular signup (regular = more intentional)
    if(any(person.properties.$initial_current_url) LIKE '%social_signup%', 1.0, 0.0) AS is_social_signup,

    -- ── Activation milestones ────────────────────────────────────────
    countIf(e.event = 'onboarding completed'
        AND e.timestamp <= now() - interval 14 day) > 0 AS completed_onboarding,
    countIf(e.event = 'first team event ingested'
        AND e.timestamp <= now() - interval 14 day) > 0 AS has_data_flowing,
    countIf(e.event = 'user logged in'
        AND e.timestamp <= now() - interval 14 day) AS login_count,

    -- ── v2 velocity features that helped (without the leaky one) ─────
    uniqIf(toDate(e.timestamp), e.timestamp <= now() - interval 14 day) AS active_days

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
