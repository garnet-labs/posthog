# Run 002: Looked at an LLM trace

**Date**: 2026-03-26
**Target**: Action 219634 — "Looked at an LLM trace"
**Status**: In progress — investigating leakage and population design

## What we predicted

P(identified user views an LLM trace detail page within 14 days) on PostHog prod project 2.

The action is a `$pageview` with URL regex `/llm-(analytics|observability)/traces/[^/?#]+`.

## First run results

| Metric    | Value                                           |
| --------- | ----------------------------------------------- |
| AUC-ROC   | **0.95**                                        |
| AUC-PR    | 0.83                                            |
| Brier     | 0.058                                           |
| Positives | 1,096                                           |
| Sampling  | 1:5 ratio (~17% positive)                       |
| Features  | 25 (9 generic + 10 LLM-specific + 6 engagement) |

Top features: `dashboard_viewed` (0.172), `llm_analytics_usage` (0.109), `events_30d` (0.106), `ai_generation_count` (0.072)

## Leakage analysis

**AUC 0.95 triggered leakage alarm.** Investigation found:

1. **`llm_analytics_usage`** (importance 0.109) — "browsed LLM analytics pages." This is near-tautological with the target. If you're on the LLM analytics page, you're one click from a trace. Not a prediction — it's the same user journey.

2. **`llma_clusters_used`**, **`llm_eval_template_selected`** — same problem. All "already in the LLM analytics section" signals.

3. **`$ai_trace` / `$ai_span`** (importance ~0.02) — SDK ingestion events, NOT UI viewing. 19.7K users/week send trace data. Probably legitimate — indicates the org has LLM observability set up.

4. **`$ai_generation`** (importance 0.072) — likely PostHog AI features (Max) or SDK ingestion. Needs investigation but probably legitimate.

## The deeper problem: population design

The real issue isn't individual features — it's **who we train on**:

- Training on ALL identified users (including existing LLMA users) → model learns "people who already use LLMA will continue using LLMA" → trivially true, useless
- The valuable prediction is: **which users who haven't used LLMA yet will start?**

This is a fundamental design choice that affects any feature adoption prediction:

| Population                                                  | Prediction                    | Value          |
| ----------------------------------------------------------- | ----------------------------- | -------------- |
| All identified users                                        | Continued usage               | Low (circular) |
| Users who never used LLMA                                   | Feature discovery             | **High**       |
| Users whose org sends `$ai_trace` but haven't viewed traces | Engagement with existing data | **High**       |
| New signups (last 30d)                                      | New user activation           | **High**       |

### Implications for the product

1. **The skill must prompt the agent to reason about population** — "are we predicting adoption or continuation?" This should happen during EDA, before feature engineering.

2. **The `brief` field on ActionPredictionConfig matters** — "predict which new users will use LLM traces" produces a fundamentally different model than "predict LLM trace usage."

3. **Population filtering belongs in the query WHERE clause** — e.g. `HAVING countIf(event = 'llm analytics usage') = 0` to exclude existing users. This is orthogonal to feature selection.

4. **This is a common footgun** — any "predict feature X adoption" target trained on everyone including heavy X users is garbage in, garbage out. The skill should warn about this pattern.

## Next steps

- [ ] Re-run excluding users who already have LLM-specific events in observation window
- [ ] Or: reframe as "predict LLMA discovery from cold" — only general PostHog usage features
- [ ] Consider whether this target is better suited to a cohort-filtered approach
- [ ] Document the population design pattern in the skill for future runs
