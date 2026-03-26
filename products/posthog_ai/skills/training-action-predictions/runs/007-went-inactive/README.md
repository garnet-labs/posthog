# Run 007: Went inactive (churn prediction)

**Date**: 2026-03-26
**Target**: Virtual label — zero `$pageview`/`$autocapture` in the 14-day label window
**Population**: Identified users with ≥100 UI events in 60-day observation window
**Base rate**: 39% (naturally balanced)

## What we predicted

P(active UI user goes completely inactive in the next 14 days) on PostHog prod project 2.

First **constructed label** — not a real event but the absence of UI events. Tests whether the framework handles virtual/dynamic action definitions. This is the most-requested ML use case in B2B SaaS: identifying at-risk users before they churn.

## Iteration comparison

| Variant     | Features | AUC-ROC | AUC-PR | Key finding                                              |
| ----------- | -------- | ------- | ------ | -------------------------------------------------------- |
| v1-baseline | 18       | 0.836   | 0.745  | Recency + consistency dominate; product depth irrelevant |

## Key learnings

1. **Constructed labels work in the framework.** The label `countIf(event IN (...) AND timestamp > T) = 0` — predicting the absence of events — works fine. No special handling needed. This opens up churn, retention, and "didn't do X" predictions.

2. **Churn prediction is fundamentally about recency and consistency, not engagement depth.** `days_since_last_ui_event` (0.372) and `ui_events_7d` (0.173) carry 55% of importance. Product engagement features (insight_viewed, dashboard_viewed, recording_viewed) are all below 0.03. A user who logs in but doesn't create insights is retained. A power user who stopped showing up is churning.

3. **Naturally balanced data is the easiest to work with.** 39% base rate means no ORDER BY trick, no balanced sampling, no calibration issues. The model trains on 50K users with 19K positives — massive reliable dataset. Highest base rate we've tested.

4. **Activity trend features have potential.** `ui_trend_week_over_week` and `ui_trend_14d` were included but didn't rank highly (both < 0.03). The raw recency (`days_since_last_ui_event`) is more powerful than the ratio. XGBoost can infer decline from the combination of ui_events_7d vs ui_events_30d.

5. **This target would pair well with the day-3 approach from Run 004.** Instead of fixed windows, per-user anchoring could score users at specific lifecycle points: "user hasn't logged in for 5 days — what's their churn probability?"

## Comparison across all runs

| Run     | Target type       | Best AUC     | Label type            | Key insight                   |
| ------- | ----------------- | ------------ | --------------------- | ----------------------------- |
| 001     | Subscribe button  | 0.80         | Action (autocapture)  | Established dev flow          |
| 002     | LLM trace         | 0.95 (leaky) | Action (pageview)     | Population design matters     |
| 003     | Insight created   | 0.90         | Simple event          | Simpler is better             |
| 004     | New user insight  | 0.77         | Event + population    | Per-user time anchoring       |
| 005     | Create alert      | 0.90         | Action (rare)         | Small sample noise            |
| 006     | Team invite       | 0.89         | Simple event          | Continuation is OK            |
| **007** | **Went inactive** | **0.84**     | **Virtual (absence)** | **Recency > depth for churn** |
