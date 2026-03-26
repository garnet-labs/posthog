-- Training query for "Looked at an LLM trace" (prod action 219634)
-- Target: P(user views an LLM trace detail page within 14 days)
-- Action matches $pageview with URL regex: /llm-(analytics|observability)/traces/[^/?#]+
--
-- Key decisions:
--   - Filter to identified users (is_signed_up = 'true')
--   - Label via IN subquery using $current_url LIKE (cheaper than elements_chain)
--   - Balanced sampling: ORDER BY label DESC, rand() — train.py takes all
--     positives + ~5-10x negatives for a ~10-17% positive rate
--   - 60-day observation window, 14-day prediction window
--   - LLM-specific features: $ai_generation, $ai_trace, $ai_evaluation counts
--
-- Temporal layout:
--   Features: [now()-74d, now()-14d]  (60-day observation window)
--   Label:    (now()-14d, now()]       (14-day prediction window)

SELECT
    person_id,

    -- ── Label (via subquery) ─────────────────────────────────────────
    if(person_id IN (
        SELECT DISTINCT person_id
        FROM events
        WHERE event = '$pageview'
          AND properties.$current_url LIKE '%/llm-%/traces/%'
          AND timestamp > now() - interval 14 day
          AND timestamp <= now()
          AND person_id IS NOT NULL
    ), 1, 0) AS label,

    -- ── Generic features ─────────────────────────────────────────────
    dateDiff('day',
        max(timestamp),
        now() - interval 14 day) AS days_since_last_event,
    count() AS events_total,
    countIf(timestamp > now() - interval 44 day) AS events_30d,
    countIf(timestamp > now() - interval 21 day) AS events_7d,
    uniq(event) AS unique_event_types,
    countIf(timestamp > now() - interval 28 day)
    / greatest(countIf(timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 28 day), 1) AS trend_ratio_14d,
    countIf(event = '$pageview')
        / greatest(count(), 1) AS pageview_ratio,
    countIf(event = '$autocapture')
        / greatest(count(), 1) AS autocapture_ratio,

    -- ── Project-specific: LLM data ingestion ─────────────────────────
    -- These indicate whether the user/org is sending LLM data to PostHog
    countIf(event = '$ai_generation') AS ai_generation_count,
    countIf(event = '$ai_trace') AS ai_trace_count,
    countIf(event = '$ai_span') AS ai_span_count,
    countIf(event = '$ai_evaluation') AS ai_evaluation_count,
    countIf(event = '$ai_metric') AS ai_metric_count,
    countIf(event = '$ai_feedback') AS ai_feedback_count,

    -- ── Project-specific: LLM analytics engagement ───────────────────
    -- Browsing LLM analytics pages (safe — upstream of viewing a trace)
    countIf(event = 'llm analytics usage') AS llm_analytics_usage,
    countIf(event = 'llm evaluation template selected') AS llm_eval_template_selected,
    countIf(event = 'llma clusters level changed') AS llma_clusters_used,
    countIf(event = 'llma provider key created') AS llma_provider_key_created,
    countIf(event = 'organization ai data processing consent toggled') AS ai_consent_toggled,

    -- ── Project-specific: general product engagement ─────────────────
    countIf(event = 'insight viewed') AS insight_viewed,
    countIf(event = 'viewed dashboard') AS dashboard_viewed,
    countIf(event = 'recording list fetched') AS recording_fetched,
    countIf(event = 'user logged in') AS user_logged_in,
    countIf(event = 'onboarding completed') AS onboarding_completed,
    countIf(event = 'product setup task completed') AS setup_tasks_completed

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now() - interval 14 day
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING events_total >= 5
ORDER BY label DESC, rand()
LIMIT 15000
