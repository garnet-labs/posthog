# v1: Baseline (19 features)

AUC-ROC: **0.901** | Features: 19 | Positives: 155 (39 in test)

Population: analytics users (identified, ≥50 events, used insights or dashboards).
90-day observation window, 30-day label window.

Top features: `unique_event_types` (0.131), `events_30d` (0.094), `alerts_page_views` (0.091), `insights_saved` (0.067), `days_since_last_event` (0.065)

**Leakage check**: `alerts_page_views` (0.091) — visiting `/alerts` page is the same page where the "Create alert" button lives. Borderline upstream-step signal. Worth ablating.

**Reliability warning**: only 39 positives in test set. AUC estimate has high variance — ±0.05 is plausible from random splits alone. Take the exact number with a grain of salt.

**Notable**: `subscriptions_created` didn't appear in importance at all (likely zero for almost everyone). `cohorts_created` barely registered (0.012). The model relies on general power-user signals (unique_event_types, events_30d, active_days) + analytics depth (insights_saved, dashboards_viewed).
