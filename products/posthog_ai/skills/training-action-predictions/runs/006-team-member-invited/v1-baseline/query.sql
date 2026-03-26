-- Training query for "team member invited" (simple named event)
-- Target: P(identified user invites a team member within 14 days)
--
-- Simple event, 1% base rate, 6K positives — clean target.
-- No population filtering needed — anyone can invite a teammate.
-- No subquery needed for label — direct event match.
--
-- Temporal layout:
--   Features: [now()-74d, now()-14d]  (60-day observation window)
--   Label:    (now()-14d, now()]       (14-day prediction window)

SELECT
    person_id,

    -- ── Label ────────────────────────────────────────────────────────
    countIf(event = 'team member invited'
        AND timestamp > now() - interval 14 day) > 0 AS label,

    -- ── Generic activity ─────────────────────────────────────────────
    countIf(timestamp <= now() - interval 14 day) AS events_total,
    countIf(timestamp > now() - interval 44 day
        AND timestamp <= now() - interval 14 day) AS events_30d,
    countIf(timestamp > now() - interval 21 day
        AND timestamp <= now() - interval 14 day) AS events_7d,
    uniqIf(event, timestamp <= now() - interval 14 day) AS unique_event_types,
    dateDiff('day',
        maxIf(timestamp, timestamp <= now() - interval 14 day),
        now() - interval 14 day) AS days_since_last_event,
    uniqIf(toDate(timestamp), timestamp <= now() - interval 14 day) AS active_days,

    -- ── Product engagement ───────────────────────────────────────────
    countIf(event = 'insight viewed'
        AND timestamp <= now() - interval 14 day) AS insight_viewed,
    countIf(event = 'insight created'
        AND timestamp <= now() - interval 14 day) AS insight_created,
    countIf(event = 'viewed dashboard'
        AND timestamp <= now() - interval 14 day) AS dashboard_viewed,
    countIf(event = 'dashboard created'
        AND timestamp <= now() - interval 14 day) AS dashboard_created,
    countIf(event = 'recording viewed'
        AND timestamp <= now() - interval 14 day) AS recording_viewed,

    -- ── Collaboration / org signals ──────────────────────────────────
    -- Prior invites in observation window (repeat behavior)
    countIf(event = 'team member invited'
        AND timestamp <= now() - interval 14 day) AS prior_invites,
    countIf(event = 'bulk invite attempted'
        AND timestamp <= now() - interval 14 day) AS bulk_invite_attempted,
    countIf(event = 'invite members button clicked'
        AND timestamp <= now() - interval 14 day) AS invite_button_clicked,

    -- ── Org growth / setup signals ───────────────────────────────────
    countIf(event = 'onboarding completed'
        AND timestamp <= now() - interval 14 day) AS onboarding_completed,
    countIf(event = 'product setup task completed'
        AND timestamp <= now() - interval 14 day) AS setup_tasks_completed,
    countIf(event = 'user signed up'
        AND timestamp <= now() - interval 14 day) AS user_signed_up,
    countIf(event = 'project create submitted'
        AND timestamp <= now() - interval 14 day) AS project_created,

    -- ── Billing / upgrade intent ─────────────────────────────────────
    countIf(event = 'pay gate shown'
        AND timestamp <= now() - interval 14 day) AS pay_gate_shown,
    countIf(event = 'billing CTA shown'
        AND timestamp <= now() - interval 14 day) AS billing_cta_shown

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 74 day
  AND timestamp <= now()
  AND person.properties.is_signed_up = 'true'
GROUP BY person_id
HAVING events_total >= 5
ORDER BY label DESC, rand()
LIMIT 15000
