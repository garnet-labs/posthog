# Run 004: New user insight creation (activation prediction)

**Date**: 2026-03-26
**Target**: `insight created` for new users only (signed up ≤14 days before label window)
**Population**: 26,363 new signups, 7.5% activation rate

## What we predicted

P(new user creates an insight in their first 14 days) on PostHog prod project 2.

This is a **population-filtered** version of run 003 — same target event but restricted to brand new users. This tests the activation prediction use case directly: which new signups will become active analytics users?

Compared to run 003 (all users, AUC 0.90), this is a much harder problem because new users have ≤14 days of behavioral history to learn from.

## Iteration comparison

| Variant        | Features | AUC-ROC   | AUC-PR    | Key finding                                              |
| -------------- | -------- | --------- | --------- | -------------------------------------------------------- |
| v1-baseline    | 16       | 0.753     | 0.449     | Honest baseline — evenly distributed importance          |
| v2-velocity    | 15       | 0.908     | 0.633     | `days_to_first_insight_view` dominates (0.41 importance) |
| v2-ablation    | 14       | 0.772     | 0.423     | Without the dominant feature — marginal improvement      |
| v3-context     | 18       | 0.746     | 0.402     | Onboarding product + signup context didn't help          |
| v4-device      | 15       | 0.760     | 0.436     | Mobile/Mac features mildly useful (+0.007 over v1)       |
| v5-exploration | 16       | 0.756     | 0.418     | Data exploration + AI usage — strong EDA, no model lift  |
| **v6-day3**    | **14**   | **0.710** | **0.514** | **3-day window only — 91% of signal at 20% of the time** |

## Key learnings

1. **New user prediction is genuinely harder** — AUC 0.75 vs 0.90 for all users. Less behavioral history means weaker signal. This is expected and the model is still useful.

2. **Velocity features help but beware of upstream-step leakage** — `days_to_first_insight_view` jumped AUC by 0.13 but it's the closest upstream action to the target. The agent (and skill) should flag this pattern: "time to first X" where X is one step before the target.

3. **`has_data_flowing` is a strong new-user signal** — whether the org ingested events is a prerequisite for insights. Binary feature, clean, non-leaky. This is the kind of activation milestone the model should learn.

4. **`active_days` captures retention** — how many distinct days a new user returned. Better than login_count for measuring stickiness.

5. **INNER JOIN for population filtering works in HogQL** — `INNER JOIN (SELECT DISTINCT person_id FROM events WHERE event = 'user signed up' AND ...) new_users ON ...` cleanly restricts to new users.

6. **Feature importance is more distributed for new users** — v1 had no feature above 0.125 (vs run 003's `events_30d` at 0.275). With less data per user, the model relies on many weak signals. This means feature pruning is less effective — the "simpler is better" finding from run 003 may not apply to thin-data populations.

## Comparison with Run 003

| Aspect            | Run 003 (all users)              | Run 004 (new users)                        |
| ----------------- | -------------------------------- | ------------------------------------------ |
| Population        | 578K identified users            | 26K new signups                            |
| Base rate         | 3.7%                             | 7.5%                                       |
| Best AUC-ROC      | 0.902 (8 features)               | 0.753 (16 features)                        |
| Feature dominance | `events_30d` at 0.275            | Distributed (max 0.124)                    |
| Pruning helps?    | Yes — 23→8 features improved AUC | Less clear — more features needed          |
| Use case          | Product engagement               | **Activation prediction**                  |
| Actionability     | Moderate                         | **High** — target onboarding interventions |
