# Run 003: Insight created

**Date**: 2026-03-26
**Target**: `insight created` (simple named event)
**Winner**: v2-simple (8 features, AUC-ROC 0.902)

## What we predicted

P(identified user creates an insight within 14 days) on PostHog prod project 2.

This is the simplest query pattern — direct `event = 'insight created'` match, no subquery needed for the label. Chosen as a clean target after run 002's leakage/population issues.

## Iteration comparison

| Variant       | Features | AUC-ROC   | AUC-PR    | Brier     | Outcome                                 |
| ------------- | -------- | --------- | --------- | --------- | --------------------------------------- |
| v1-baseline   | 23       | 0.889     | 0.703     | 0.081     | Good but noisy                          |
| **v2-simple** | **8**    | **0.902** | **0.688** | **0.083** | **Winner — simpler and better**         |
| v3-enriched   | 17       | 0.883     | 0.691     | 0.086     | Person props + query events didn't help |
| v4-ratios     | 11       | 0.899     | 0.697     | 0.082     | Tied — XGBoost learns ratios implicitly |

## Winning model (v2-simple)

8 features, all with clear signal:

| Feature                 | Importance | Type                            |
| ----------------------- | ---------- | ------------------------------- |
| `events_30d`            | 0.275      | Generic — recent activity       |
| `insight_viewed`        | 0.162      | Engagement — viewing insights   |
| `dashboard_viewed`      | 0.151      | Engagement — using dashboards   |
| `unique_event_types`    | 0.118      | Generic — breadth of usage      |
| `events_7d`             | 0.094      | Generic — very recent activity  |
| `insight_analyzed`      | 0.071      | Engagement — analyzing insights |
| `days_since_last_event` | 0.069      | Generic — recency               |
| `events_total`          | 0.061      | Generic — total volume          |

## Key learnings

1. **Simpler models can be more accurate** — dropping 15 weak features improved AUC from 0.889 to 0.902. When signal is concentrated in a few features, extra features add noise.

2. **Person properties didn't help for this target** — team size, project count, org count are static attributes that don't predict behavioral actions well. Behavioral features (what the user DID) beat demographic features (what the org IS).

3. **Query events are redundant with activity counts** — `query_executed`/`query_completed` are just another way of measuring general activity, already captured by `events_30d`.

4. **Simple named events are the cleanest targets** — no subquery, no LIKE, no URL matching. Just `event = 'X'` in the label. The agent should prefer these when available.

5. **HogQL person property gotchas** — need `any()` wrapper in GROUP BY queries, `toFloatOrDefault` needs `0.0` not `0` as default type.

6. **3.7% base rate doesn't need ORDER BY trick** — natural LIMIT 50000 sampling yields ~1,500 positives. The balanced sampling in train.py handles the rest. The `ORDER BY label DESC, rand()` pattern is only needed for very rare events (< 0.5%).

7. **XGBoost learns ratios implicitly** — v4 added explicit behavioral ratios (insight_view_ratio, acceleration) but AUC was tied with v2. Tree-based models can approximate ratios via splits on the raw features. Explicit ratios might matter more for linear models.

## Scoring (predict.py)

Scored 50,000 identified users and sent `$ai_prediction` events to local PostHog.

**Read/write split**: predict.py reads from prod (`POSTHOG_HOST=us.posthog.com`) for scoring data, writes to local (`POSTHOG_CAPTURE_HOST=localhost:8010`) for events. This avoids writing test predictions to prod.

**Query adaptation**: predict.py automatically transforms the training query for scoring — strips the label column and shifts the time window from T-14d to T=now. No separate scoring query file needed.

Score distribution:

| Bucket      | Users  | %     |
| ----------- | ------ | ----- |
| very_likely | 3,423  | 6.8%  |
| likely      | 7,364  | 14.7% |
| neutral     | 7,286  | 14.6% |
| unlikely    | 31,927 | 63.9% |

Person properties set: `p_action_insight_created` (probability), `p_action_insight_created_bucket` (bucket).
