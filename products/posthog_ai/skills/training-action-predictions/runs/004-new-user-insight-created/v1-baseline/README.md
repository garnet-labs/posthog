# v1: Baseline (16 features)

AUC-ROC: **0.753** | Features: 16 (4 generic + 3 engagement + 5 onboarding + 4 early exploration)

Baseline with a mix of generic activity, analytics engagement (carried over from run 003), onboarding signals, and early product exploration features.

Feature importance is more evenly distributed than run 003 — no single feature dominates. This is expected: new users have less behavioral history so the model relies on many weak signals rather than a few strong ones.

Top features: `days_since_last_event` (0.124), `events_7d` (0.104), `insight_analyzed` (0.097), `insight_viewed` (0.084), `dashboard_viewed` (0.062)
