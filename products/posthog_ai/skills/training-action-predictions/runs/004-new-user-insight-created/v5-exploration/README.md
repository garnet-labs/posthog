# v5: Data exploration + AI usage (16 features)

AUC-ROC: **0.756** | Features: 16 (v1 core + data exploration + AI tools + SDK doctor + velocity)

Hypothesis: new users who actively explore their data model (search events, hover definitions, browse event definitions) and use AI tools (Max) are showing "learning intent" that predicts insight creation.

**EDA showed very strong population-level signal**:

- `event definitions page load succeeded` → 22.9% activation (3x baseline)
- `taxonomic_filter_search_query` → 19.9% (2.6x)
- `ai mode executed` → 18.8% (2.5x)
- `definition hovered` → 17.2% (2.3x)

**Result**: AUC 0.756 — on par with v1 (0.753), did not improve.

**Why strong EDA signal doesn't translate to model improvement**: this is now a consistent pattern across v3, v4, and v5. Population-level activation rate differences (2-3x baseline) look dramatic but:

1. **The features are too correlated with general activity** — users who search for events, hover definitions, and use AI tools also have higher `events_7d` and `unique_event_types`. XGBoost already captures this via the existing behavioral features.

2. **Binary/sparse features are weak predictors** — `visited_event_definitions` and `used_sdk_doctor` are 0/1 flags for most users. They can only split the population once. The continuous behavioral features (events_7d, insight_analyzed) provide much finer-grained splits.

3. **New user data is inherently noisy** — with ≤14 days of behavior, there's a ceiling on how much signal any feature set can extract. The core model at 0.75 AUC may be close to the practical limit for this population and time window.

**Emerging conclusion for run 004**: the v1 behavioral baseline (0.753) is remarkably robust. Three rounds of feature enrichment (context, device, exploration) have each added <0.01 AUC. The v2 ablation (0.772) remains the best honest model, and its improvement comes from `active_days` and `has_data_flowing` — simple structural features, not complex metadata.
