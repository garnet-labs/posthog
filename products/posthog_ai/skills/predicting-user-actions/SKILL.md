---
name: predicting-user-actions
description: 'Score users with a trained action prediction model and make predictions actionable. Creates person properties with probability scores and bucket labels, builds cohorts for targeting, and reports score distributions. Use when the user asks to score users, get predictions, find who will convert, create a prediction cohort, or identify users likely to perform an action.'
---

# Predicting user actions

Given a trained `ActionPredictionModel` with a winning `ActionPredictionModelRun`, score all eligible users and make predictions actionable through person properties and cohorts.

## Prerequisites

- A trained model must exist — check via `action-prediction-model-list` and `prediction-model-run-list`
- At least one run should have `is_winning: true` with valid `artifact_script` and `metrics`
- If no trained model exists, suggest running the `training-action-predictions` skill first

## Workflow

### Step 1: Load the winning model

1. List models via `action-prediction-model-list` to find the target model
2. List runs via `prediction-model-run-list` and find the run where `is_winning: true`
3. Extract:
   - The `artifact_script` (the training script — contains the feature extraction logic)
   - The `metrics` (to report model quality alongside predictions)
   - The `feature_importance` (to explain which features drive predictions)

If no winning run exists, list all runs and pick the one with the highest `metrics.auc_roc`.

### Step 2: Extract features for scoring

Run the same feature extraction query used during training, but with `T = now()` (no label window needed for scoring).

Adapt the query from the winning run's training context:

```sql
SELECT
    person_id,
    -- Same features as training, but observation window is [now()-90d, now()]
    -- No label column needed
    dateDiff('day', max(timestamp), now()) AS days_since_last_event,
    count() AS events_total_90d,
    countIf(timestamp > now() - interval 30 day) AS events_30d,
    countIf(timestamp > now() - interval 7 day) AS events_7d,
    -- ... all other features from the training query
    ...
FROM events
WHERE team_id = currentTeamId()
  AND person_id IS NOT NULL
  AND timestamp >= now() - interval 90 day
GROUP BY person_id
HAVING events_total_90d >= 5
```

The feature columns **must match** the training features exactly (same names, same order). Check the winning run's `feature_importance` keys to verify alignment.

### Step 3: Score users

Run the scoring script against the feature matrix. The script should:

1. Load the feature matrix from the HogQL query output
2. Apply the trained model (from `artifact_script`)
3. Generate calibrated probabilities for each user
4. Assign bucket labels based on probability thresholds

See [scoring script template](./references/scoring-script-template.md) for the baseline.

### Step 4: Write person properties

For each scored user, set two person properties:

| Property                 | Type   | Value                                                  |
| ------------------------ | ------ | ------------------------------------------------------ |
| `p_action_{name}`        | float  | Calibrated probability 0.0–1.0                         |
| `p_action_{name}_bucket` | string | One of: `very_likely`, `likely`, `neutral`, `unlikely` |

Bucket thresholds:

- `very_likely`: probability >= 0.7
- `likely`: 0.4 <= probability < 0.7
- `neutral`: 0.15 <= probability < 0.4
- `unlikely`: probability < 0.15

Write properties via the PostHog capture API or batch person property set (`persons-property-set`).

### Step 5: Create cohorts

Create dynamic cohorts using the person properties:

```text
cohorts-create(
  name="Likely to {action}",
  groups=[{"properties": [{"key": "p_action_{name}", "value": 0.5, "operator": "gte", "type": "person"}]}]
)
```

Standard cohorts to create:

- **Likely to {action}**: `p_action_{name} >= 0.5`
- **Unlikely to {action}**: `p_action_{name} < 0.2`
- **On the fence for {action}**: `0.2 <= p_action_{name} < 0.5`

### Step 6: Report

Produce a summary for the user:

```markdown
## Prediction Report: {model_name}

**Model quality**: AUC-ROC {value} ({signal_quality}) | AUC-PR {value} | Brier {value}

### Score Distribution

| Bucket             | Count | %      |
| ------------------ | ----- | ------ |
| Very likely (≥0.7) | {n}   | {pct}% |
| Likely (0.4–0.7)   | {n}   | {pct}% |
| Neutral (0.15–0.4) | {n}   | {pct}% |
| Unlikely (<0.15)   | {n}   | {pct}% |
| **Total scored**   | {n}   | 100%   |

### Top 20 Most Likely Users

| Person                     | Probability | Top feature      |
| -------------------------- | ----------- | ---------------- |
| {person_id or distinct_id} | {prob}      | {feature: value} |

### What You Can Do Now

- **Persons list**: filter by `p_action_{name}` to see scored users
- **Cohorts**: three cohorts created — use in insights, flags, or experiments
- **Feature flags**: target by `p_action_{name} > 0.6` for interventions
- **Experiments**: test messaging on the "on the fence" cohort
- **Insights**: break down funnels/trends by prediction bucket
```

## Free surfaces

Once predictions are person properties, these work automatically with zero extra code:

- **Persons list**: filter and sort by prediction score
- **Cohorts**: dynamic cohorts on the person property
- **Insights**: trends, funnels, retention filtered by prediction bucket
- **Feature flags**: target users by `p_action_{name} > threshold`
- **Experiments**: test interventions on predicted-likely vs unlikely cohorts

## Guardrails

- **Feature alignment**: scoring features must exactly match training features — mismatches cause silent errors
- **Stale scores**: predictions degrade over time as user behavior changes. Note the scoring date in the report
- **Model quality**: always report the model's AUC-ROC alongside predictions. If signal quality is "red" (<0.65), warn the user that predictions are low-confidence
- **Property naming**: always use the `p_action_` prefix for prediction properties to avoid conflicts
