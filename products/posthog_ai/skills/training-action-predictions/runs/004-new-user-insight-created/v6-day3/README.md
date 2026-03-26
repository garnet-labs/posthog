# v6: Day 3 prediction with per-user time anchoring (14 features)

AUC-ROC: **0.710** | Features: 14 | Feature window: **3 days only**

Hypothesis: predict insight creation at day 3 using per-user time anchoring. Each user's features are computed relative to THEIR signup time (not a fixed global T). This is how scoring would work in production.

**Key design: per-user time travel**

Instead of a fixed observation window like `[now-28d, now-14d]`, each user gets:

- Features: `[signup_time, signup_time + 3 days]`
- Label: `(signup_time + 3 days, signup_time + 17 days]`

This gives us ALL signups from the last 45 days as training data (where we have 17+ days of outcome), not just a narrow slice. Result: 4,244 positives — 2x more than the fixed-window v1.

**HogQL pattern**: INNER JOIN subquery to get `signup_time`, then use `su.signup_time + interval N day` in all countIf/dateDiff filters. GROUP BY must include `su.signup_time`.

**Result**: AUC 0.710 from only 3 days of behavior. Only 0.04 AUC below the 14-day model (0.753). This means 91% of the predictive signal available at day 14 is already present at day 3.

**Comparison with previous iterations:**

| Model        | Feature window | AUC-ROC   | Actionability                     |
| ------------ | -------------- | --------- | --------------------------------- |
| v1 (14 days) | 14 days        | 0.753     | Low — too late to intervene       |
| v6 (3 days)  | **3 days**     | **0.710** | **High — early onboarding nudge** |

**Top features** — similar to 14-day model but compressed:

- `insight_viewed` (0.210) — did they explore insights in first 3 days?
- `dashboard_viewed` (0.118) — did they look at dashboards?
- `insight_analyzed` (0.077) — did they analyze an insight?
- `events_total` (0.070) — overall activity volume
- `active_days` (0.059) — came back on multiple of the 3 days?

**Key insight for the product**: per-user time anchoring is the correct approach for lifecycle predictions. The fixed-window approach (v1-v5) was a simplification that loses data and misaligns feature windows. The skill should default to per-user anchoring for any target that relates to user lifecycle stage.

**Trade-off**: the query is more complex (INNER JOIN + per-user timestamp arithmetic) but produces better training data and matches the production scoring pattern exactly.
