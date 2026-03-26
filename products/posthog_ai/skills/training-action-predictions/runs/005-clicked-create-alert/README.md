# Run 005: Clicked Create Alert

**Date**: 2026-03-26
**Target**: Action 253406 — "Clicked Create Alert" (`$autocapture`, text "Create alert", URL `/alerts`)
**Population**: Analytics users (identified, ≥50 events, used insights or dashboards)
**Label window**: 30 days (alerts are naturally rare)

## What we predicted

P(analytics power user clicks "Create alert" within 30 days) on PostHog prod project 2.

This is a **rare feature adoption** prediction — only ~155 users out of 181K analytics users create alerts in a 30-day window (0.09% base rate). Chosen as a stress test for extreme class imbalance.

## Population design

Alert creators are extreme power users (37K avg events vs 2.6K for typical identified users). Training on all identified users would waste the model on 99.97% of users who'd never discover alerts. Instead, we restrict to "analytics users" — people who already use insights/dashboards and thus _could_ create alerts.

## Iteration comparison

| Variant     | Features | AUC-ROC | AUC-PR | Positives | Key finding                                     |
| ----------- | -------- | ------- | ------ | --------- | ----------------------------------------------- |
| v1-baseline | 19       | 0.901   | 0.687  | 155       | Good but only 39 test positives — high variance |

## Key learnings

1. **Rare events need wider label windows** — 14-day window yields ~100 positives, 30-day yields ~155. Still thin but workable with balanced sampling.

2. **Population filtering is critical for rare features** — restricting from 578K to 181K analytics users made the prediction meaningful. Among all users, it's 0.018% (impossible). Among analytics users, it's 0.09% (still hard but the features are relevant).

3. **Small test sets mean noisy metrics** — 39 positives in the test set. AUC 0.90 could easily be 0.85 or 0.95 on a different split. Need to note this in model cards. Cross-validation would be more reliable here.

4. **`alerts_page_views` is borderline leaky** — visiting the alerts page is one click from creating an alert. Same upstream-step pattern from Run 002/004. Needs ablation.
