# v1: Baseline (23 features)

AUC-ROC: **0.889** | Features: 23 (9 generic + 14 project-specific)

Full kitchen-sink feature set: generic activity features, product engagement events (insights, dashboards, recordings), onboarding events, collaboration events (invites, flag creation), billing intent.

**Observation**: 15 of 23 features clustered tightly around 0.025 importance — barely contributing. The top 5 features carry most of the signal. This motivated v2 (simplification) and v3 (targeted enrichment).
