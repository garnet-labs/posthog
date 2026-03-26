# v2: Simplified (8 features) — WINNER

AUC-ROC: **0.902** | Features: 8 (5 generic + 3 product engagement)

Dropped all features with importance < 0.03 from v1. Kept only:

- `events_total`, `events_30d`, `events_7d`, `unique_event_types`, `days_since_last_event`
- `insight_analyzed`, `dashboard_viewed`, `insight_viewed`

**Result**: AUC improved from 0.889 → 0.902 by removing noise. Each remaining feature now has stronger, clearer importance. The model is simpler, faster, and more accurate.

**Lesson**: when signal is concentrated in a few features, adding more features hurts. Simpler is better. This validates the skill's simplicity criterion.
