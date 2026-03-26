# v4: Combined — recency + decay pattern (15 features) — WINNER

AUC-ROC: **0.845** | AUC-PR: **0.757** | Features: 15

Best of both worlds: the dominant `days_since_last_ui_event` from v1/v2 PLUS the weekly decay pattern features from v3.

**Result**: AUC 0.845 — best across all variants. The recency and decay features are complementary, not redundant:

- `days_since_last_ui_event` (0.251) answers "are they gone?"
- `ui_week_1` (0.241) answers "how active were they recently?"
- `weeks_active` (0.115) answers "were they consistent?"
- `recent_vs_earlier_ratio` (0.059) answers "are they fading?"

The model uses recency for the obvious cases (user gone for 10+ days) and decay patterns for the ambiguous ones (user was here 2 days ago but activity has been declining for weeks).

**Lesson**: when a dominant feature is legitimate (not leaky), keep it AND add complementary features. Don't ablate for purity — combine for accuracy.
