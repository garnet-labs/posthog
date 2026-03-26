-- Training query for "Subscribe button clicked" (prod action 142194)
-- Target: P(user clicks subscribe/upgrade CTA within 14 days)
--
-- Key decisions:
--   - Filter to identified users only (is_signed_up = 'true')
--   - Label via IN subquery (cheap: LIKE scan only on 14d label window)
--   - Balanced sampling: ORDER BY label DESC, rand() so all positives
--     come first, rest filled with negatives. Train.py then takes all
--     positives + equal negatives. Isotonic calibration adjusts probs
--     back to the true base rate.
--   - 60-day observation window, 14-day prediction window
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
        WHERE event = '$autocapture'
          AND (elements_chain LIKE '%billing-page-core-upgrade-cta%'
               OR elements_chain LIKE '%billing-page-addon-cta-upgrade-cta%'
               OR elements_chain LIKE '%onboarding-subscribe-button%')
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

    -- ── Project-specific: billing/upgrade intent ─────────────────────
    countIf(event = 'pay gate shown') AS pay_gate_shown,
    countIf(event = 'upgrade modal shown') AS upgrade_modal_shown,
    countIf(event = 'billing CTA shown') AS billing_cta_shown,
    countIf(event = 'billing alert action clicked') AS billing_alert_clicked,
    countIf(event = 'pay gate CTA clicked') AS pay_gate_cta_clicked,
    countIf(event = 'user showed product intent') AS product_intent_shown,

    -- ── Project-specific: product engagement ─────────────────────────
    countIf(event = 'insight viewed') AS insight_viewed,
    countIf(event = 'insight analyzed') AS insight_analyzed,
    countIf(event = 'viewed dashboard') AS dashboard_viewed,
    countIf(event = 'recording list fetched') AS recording_fetched,
    countIf(event = 'user logged in') AS user_logged_in,

    -- ── Project-specific: onboarding ─────────────────────────────────
    countIf(event = 'onboarding started') AS onboarding_started,
    countIf(event = 'onboarding completed') AS onboarding_completed,
    countIf(event = 'product setup task completed') AS setup_tasks_completed,
    countIf(event = 'user signed up') AS user_signed_up

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now() - interval 14 day
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING events_total >= 5
ORDER BY label DESC, rand()
LIMIT 5000
