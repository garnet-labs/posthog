# Run 001: Subscribe button clicked

**Date**: 2026-03-26
**Target**: Action 142194 — "Subscribe button clicked"
**Config**: `019d29f3-84f4-788e-adaa-c38ad4a047d2` (local PostHog)
**Model**: `019d2a2a-0efd-72ed-90fe-c05c5877af5f` (local PostHog, winning model)

## What we predicted

P(identified user clicks subscribe/upgrade CTA within 14 days) on PostHog prod project 2.

The action is autocapture-based, matching clicks on billing upgrade CTAs (`billing-page-core-upgrade-cta`, `billing-page-addon-cta-upgrade-cta`) and onboarding subscribe buttons (`onboarding-subscribe-button`).

## Results

| Metric    | Value                                |
| --------- | ------------------------------------ |
| AUC-ROC   | **0.80** (green)                     |
| AUC-PR    | 0.79                                 |
| Brier     | 0.186                                |
| Positives | 946                                  |
| Sampling  | 50/50 balanced                       |
| Features  | 23 (9 generic + 14 project-specific) |

Top features: `billing_cta_shown` (0.106), `autocapture_ratio` (0.086), `onboarding_started` (0.076), `pageview_ratio` (0.071), `unique_event_types` (0.063)

## Iterations (chronological)

1. **Full scan query → 504 timeout**. `elements_chain LIKE` in main aggregation across 104 days of prod data. Fix: move label to `IN` subquery scanning only 14-day window.

2. **LEFT JOIN for labels → all label=1**. HogQL/ClickHouse LEFT JOIN + NULL check didn't work as expected. Fix: use `IN` subquery.

3. **Unfiltered LIMIT 20K → 7 positives**. 93% of prod users are anonymous. Base rate 0.03%. Fix: add `person.properties.is_signed_up = 'true'` filter.

4. **Identified + LIMIT 50K → 76 positives, AUC 0.69**. 0.15% base rate among identified users. XGBoost starved of positive examples. Fix: balanced sampling.

5. **Balanced sampling → 946/946, AUC 0.80**. `ORDER BY label DESC, rand()` in HogQL. This is the pattern.

## Key learnings for the feature

- **Identified users filter is essential** — 93% of users are anonymous noise, must filter to `is_signed_up = 'true'` or equivalent
- **Balanced sampling needed for rare events** — `ORDER BY label DESC, rand()` in HogQL + Python downsampling
- **Action-based targets (autocapture + selectors) need IN subquery** — `elements_chain LIKE` is too expensive for main aggregation
- **`$current_url` matching is cheaper** than `elements_chain LIKE` for pageview-based actions
- **Query timeout on prod** — bumped utils.py from 120s to 300s
