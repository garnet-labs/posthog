# v1: Baseline (20 features)

AUC-ROC: **0.893** | Features: 20 | Positives: 6,068 (1,517 in test)

Simple named event, all identified users with ≥5 events, 14-day label window.

Top features: `prior_invites` (0.232), `unique_event_types` (0.171), `bulk_invite_attempted` (0.136), `events_30d` (0.067)

**This is a continuation model** — the strongest signal is past invite behavior. People who already invited will invite again. This is honest and useful (predicting repeat expansion behavior) but different from predicting first-time invite.

No leakage concerns — `prior_invites` is past behavior in the observation window, not the label window. It's legitimate signal, just not "novel adoption" prediction.
