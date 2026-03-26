# v2: Simplified (5 features)

AUC-ROC: **0.838** | Features: 5

Dropped 13 features, kept only top 5 from v1. Same AUC (0.838 vs 0.836). `days_since_last_ui_event` concentrates to 0.635 importance — the model is essentially "when did they last visit?"

Confirms the run 003 pattern: simpler is equal or better when signal is concentrated. For churn, 5 features carry all the information.
