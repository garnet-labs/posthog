# v1: Baseline (18 features)

AUC-ROC: **0.836** | Features: 18 | Positives: 19,435 (4,859 in test) | Base rate: 39%

First constructed/virtual label — predicting absence of UI events, not a specific event.
Naturally balanced (~40/60 split), no ORDER BY trick needed, massive training data.

Top features: `days_since_last_ui_event` (0.372), `ui_events_7d` (0.173), `active_days` (0.096)

**Key finding**: for churn prediction, recency and consistency dominate everything else. Product engagement depth (what they did) barely matters — what matters is whether they're still showing up. This is fundamentally different from activation prediction (Run 004) where engagement features were important.

No leakage concerns. `days_since_last_ui_event` is the observation window's last activity timestamp, cleanly separated from the label window.
