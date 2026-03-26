# v3: Decay pattern (13 features, no trivial recency)

AUC-ROC: **0.840** | Features: 13

Removed `days_since_last_ui_event` (the trivially dominant feature) and replaced with weekly activity buckets to capture the SHAPE of activity decline.

**Result**: AUC 0.840 — matches v1 without the recency crutch. And the features tell a richer story:

| Feature                   | Importance | What it captures                                   |
| ------------------------- | ---------- | -------------------------------------------------- |
| `ui_week_1`               | 0.269      | Most recent week's activity (low = danger)         |
| `weeks_active`            | 0.167      | How many of 8 weeks had any activity (consistency) |
| `recent_vs_earlier_ratio` | 0.158      | Recent 2 weeks / prior 4 weeks (fading signal)     |
| `active_days`             | 0.138      | Distinct days active                               |

**Key finding**: the decay SHAPE matters as much as raw recency. A user who was active 8/8 weeks but had a declining trend is different from one active 4/8 weeks with stable activity. The model can capture this from weekly buckets without the trivial "last login" feature.

**`recent_vs_earlier_ratio` is genuine new signal** — it captures "fading out" explicitly. Users whose recent activity is a small fraction of their earlier activity are churning even if they were recently active.

**Implication for the product**: weekly activity bucketing is a powerful pattern for any time-series-like prediction. The agent should consider temporal decomposition (weekly/daily buckets) when the target is about behavioral change over time, not just one-time actions.
