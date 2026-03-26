---
name: training-action-predictions
description: 'Train a predictive model for user actions using an autonomous experiment loop. Explores project data via HogQL, engineers features, trains XGBoost models with iterative refinement, and records results as prediction model runs. Use when the user asks to predict an action, train a prediction model, build a propensity score, or predict conversion/churn/upgrade.'
---

# Training action predictions

Build a model that predicts P(user performs action X within W days). Uses an autonomous experiment loop inspired by [autoresearch](https://github.com/karpathy/autoresearch) — explore data, engineer features, train, evaluate, keep or discard, repeat.

## Prerequisites

- An `ActionPredictionModel` must exist (create one via `action-prediction-model-create` if needed)
- The project must have sufficient event data (≥500 users, ≥50 positive examples)

## Workflow

### Phase 1: Setup

1. If no `ActionPredictionModel` exists for the target, create one:

   ```text
   action-prediction-model-create(
     name="Predict upgraded_plan",
     event_name="upgraded_plan",   # or action=<id>
     lookback_days=7
   )
   ```

2. Note the returned model ID — all runs will reference it.

### Phase 2: Data discovery

Use `execute-sql` with HogQL to understand the project's data before engineering features. Run these queries:

1. **Active users**: `SELECT uniq(person_id) FROM events WHERE timestamp >= now() - interval 90 day`
2. **Top events**: `SELECT event, count() as c FROM events WHERE timestamp >= now() - interval 90 day GROUP BY event ORDER BY c DESC LIMIT 20`
3. **Base rate**: `SELECT countIf(event = '{target}') > 0 as converted, count() FROM (SELECT person_id, countIf(event = '{target}' AND timestamp >= now() - interval {W} day) > 0 as converted FROM events WHERE timestamp >= now() - interval 90 day GROUP BY person_id HAVING count() >= 5) GROUP BY converted`
4. **Person properties**: `properties-list` to discover available properties
5. **Session distribution**: `SELECT count(), avg(duration) FROM sessions WHERE min_timestamp >= now() - interval 90 day`

Report findings to the user before proceeding. This is the one pause point.

**Stop conditions**: If base rate < 1% or fewer than 50 positive examples, warn the user — model quality will be limited. If fewer than 500 users, refuse to train.

### Phase 3: Feature engineering

Write a HogQL feature extraction query. The key constraint is **temporal correctness** — features must come from before the label window.

See [baseline feature query](./references/baseline-feature-query.md) for the starting point.

The agent iterates on this query across experiments — adding features, removing noise, testing different windows.

**Feature ideas to explore** (in roughly this priority):

1. Per-event ratios for top-10 events by volume
2. Session features: avg duration, pageviews/session, bounce rate
3. Temporal dynamics: week-over-week trend, day-of-week patterns
4. Navigation: unique URLs, entry/exit patterns
5. Person properties as features (plan type, signup source)
6. Feature interactions (domain-specific)

### Phase 4: Training

Write a Python training script and record it as a prediction model run. The script should:

1. Accept the feature matrix as CSV/JSON input
2. Train XGBoost with `scale_pos_weight` for class imbalance
3. Use time-based cross-validation (3 folds with temporal gap)
4. Apply isotonic calibration for probability calibration
5. Evaluate: AUC-ROC (primary), AUC-PR, Brier score
6. Output metrics and feature importance as JSON

See [training script template](./references/training-script-template.md) for the baseline.

Upload the trained model artifact and record the run:

1. **Get a presigned upload URL** from the config:

   ```text
   action-prediction-config-upload-url(config_id=<config_id>, filename="model.pkl")
   → { url, fields, storage_path }
   ```

2. **Upload the serialized model** (e.g. pickled XGBoost) to the presigned URL using the returned `url` and `fields`.

3. **Record the run** with `storage_path` as `model_url`:

   ```text
   action-prediction-model-create(
     config=<config_id>,
     is_winning=false,
     model_url="<storage_path from step 1>",
     metrics={"auc_roc": 0.72, "auc_pr": 0.19, "brier": 0.08},
     feature_importance={"days_since_last_event": 0.15, ...},
     artifact_script="<the full Python script>"
   )
   ```

Every trained model **must** be uploaded to S3 before recording. Never leave `model_url` empty — the artifact is required for scoring.

### Phase 5: Experiment loop (autonomous)

Once the baseline is established, loop autonomously:

```text
LOOP (max 10 experiments or 3 consecutive non-improvements):
  1. Review previous runs — what features/params helped, what didn't
  2. Formulate hypothesis: new features, hyperparameter change, feature selection
  3. Modify the feature query and/or training script
  4. Execute:
     a. Run feature query via execute-sql
     b. Run training script
     c. Upload model artifact to S3 via action-prediction-config-upload-url
     d. Record run via action-prediction-model-create with the storage_path as model_url
  5. Compare AUC-ROC to current best:
     → Improved: mark this run as winning (action-prediction-model-partial-update, is_winning=true)
     → Equal or worse: leave is_winning=false
  6. Continue to next experiment
```

**Experiment ideas** (after baseline):

- Hyperparameter sweep: max_depth ∈ {4,6,8}, learning_rate ∈ {0.05,0.1,0.2}
- Feature selection: drop features with importance < 0.01
- Calibration: isotonic vs sigmoid, compare Brier scores
- More training data: extend observation window from 90d to 180d

### Phase 6: Post-training guardrails

**Run these checks before completing. Do not finish until all pass.**

1. Call `action-prediction-model-list` filtered to this config.
2. Walk through the table top-to-bottom — stop at the first matching condition:

| #   | Condition                                      | Severity  | Action                                                                                                                     |
| --- | ---------------------------------------------- | --------- | -------------------------------------------------------------------------------------------------------------------------- |
| G1  | No models exist for this config                | **Fatal** | Stop. Fail the task with error: "Training produced no models."                                                             |
| G2  | Models exist but none has `is_winning: true`   | **Steer** | Pick the model with the highest `metrics.auc_roc` and set `is_winning: true` via `action-prediction-model-partial-update`. |
| G3  | Winning model has empty or missing `model_url` | **Steer** | Re-upload the artifact via `action-prediction-config-upload-url` and update `model_url` on the winning model.              |
| G4  | Winning model has empty `artifact_script`      | **Steer** | Re-record the training script text on the winning model via `action-prediction-model-partial-update`.                      |
| G5  | All checks pass                                | **Pass**  | Proceed to model card.                                                                                                     |

After each steer action, re-run all checks from G1.
If the same guardrail triggers twice consecutively, escalate to fatal.

### Phase 7: Model card

After guardrails pass, produce a summary:

```markdown
## Model Card: {model_name}

- Target: P(user does {event} within {W} days)
- Best AUC-ROC: {value} | AUC-PR: {value} | Brier: {value}
- Signal Quality: green (>0.75) / yellow (0.65-0.75) / red (<0.65)
- Base Rate: {pct}%
- Training: {n} users ({pos} positive)
- Top 5 Features: {ranked list}
- Experiments: {n} run, {n_winning} improvements found
```

## Guardrails

- **Leakage prevention**: always exclude the target event from features; observation window strictly before label window
- **Calibration**: always apply isotonic calibration
- **Features**: aim for 15-40. More than 50 risks overfitting
- **Imbalance**: always use `scale_pos_weight`, never downsample
- **Reproducibility**: seed=42, every experiment recorded as a model run
