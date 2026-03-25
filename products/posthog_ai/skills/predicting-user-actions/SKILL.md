---
name: predicting-user-actions
description: 'Score users with a trained action prediction model and make predictions actionable. Creates person properties with probability scores and bucket labels, builds cohorts for targeting, and reports score distributions. Use when the user asks to score users, get predictions, find who will convert, create a prediction cohort, or identify users likely to perform an action.'
---

# Predicting user actions

Given a trained `ActionPredictionModel` with a winning `ActionPredictionModelRun`, score all eligible users and make predictions actionable through person properties and cohorts.

## Prerequisites

- A trained model must exist — check via `action-prediction-model-list` and `prediction-model-run-list`
- At least one run should have `is_winning: true` with valid `artifact_scripts` and `metrics`
- If no trained model exists, suggest running the `training-action-predictions` skill first

## Reference scripts

The prediction script is in `training-action-predictions/references/`:

- **`predict.py`** — fetches scoring data via PostHog API, loads pipeline, scores users
- **`utils.py`** — shared `execute_hogql()` and `fetch_features()` helpers

## Workflow

### Step 1: Load the winning model

1. List models via `action-prediction-model-list` to find the target model
2. List runs via `prediction-model-run-list` and find the run where `is_winning: true`
3. Extract from the run:
   - `artifact_scripts.query` — the HogQL training query (adapt for scoring)
   - `artifact_scripts.utils` — the shared utils.py (execute_hogql, fetch_features)
   - `artifact_scripts.predict` — the predict.py script
   - `metrics` — to report model quality alongside predictions
   - `feature_importance` — to explain which features drive predictions

If no winning run exists, pick the one with the highest `metrics.auc_roc`.

### Step 2: Run the prediction script

The `predict.py` script is self-contained — it fetches its own data and scores users:

1. Write `utils.py` from `artifact_scripts.utils`
2. Adapt the training query for scoring: set `T = now()`, remove the label column
3. Write the adapted `predict.py` script from `artifact_scripts.predict`
4. Execute it — produces `scores.parquet` and `scores.json`

The sklearn Pipeline in `model.pkl` handles all preprocessing internally, so feature alignment is guaranteed as long as the scoring query produces the same column names as training.

### Step 3: Write person properties

For each scored user, set two person properties via `persons-property-set`:

| Property                 | Type   | Value                                                  |
| ------------------------ | ------ | ------------------------------------------------------ |
| `p_action_{name}`        | float  | Calibrated probability 0.0–1.0                         |
| `p_action_{name}_bucket` | string | One of: `very_likely`, `likely`, `neutral`, `unlikely` |

Bucket thresholds:

- `very_likely`: probability >= 0.7
- `likely`: 0.4 <= probability < 0.7
- `neutral`: 0.15 <= probability < 0.4
- `unlikely`: probability < 0.15

### Step 4: Create cohorts

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

### Step 5: Report

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

Once predictions are person properties, these work automatically:

- **Persons list**: filter and sort by prediction score
- **Cohorts**: dynamic cohorts on the person property
- **Insights**: trends, funnels, retention filtered by prediction bucket
- **Feature flags**: target users by `p_action_{name} > threshold`
- **Experiments**: test interventions on predicted-likely vs unlikely cohorts

## Guardrails

- **Feature alignment**: scoring query must produce the same column names as training — the sklearn Pipeline handles the rest
- **Stale scores**: predictions degrade over time. Note the scoring date in the report
- **Model quality**: always report AUC-ROC alongside predictions. If signal quality is "red" (<0.65), warn the user
- **Property naming**: always use the `p_action_` prefix for prediction properties
- **HogQL**: do not use `currentTeamId()` (MCP scopes automatically), always add `LIMIT 50000`
