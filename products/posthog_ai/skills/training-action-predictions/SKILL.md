---
name: training-action-predictions
description: 'Train a predictive model for user actions using an autonomous experiment loop. Explores project data via HogQL, engineers features, trains XGBoost models with iterative refinement, and records results as prediction model runs. Use when the user asks to predict an action, train a prediction model, build a propensity score, or predict conversion/churn/upgrade.'
---

# Training action predictions

Build a model that predicts P(user performs action X within W days). Uses an autonomous experiment loop — explore data, write a HogQL feature query, train an sklearn Pipeline, evaluate, iterate.

All feature engineering is pushed down to ClickHouse via HogQL. The query returns `person_id, label, features` — Python just trains the model.

## Prerequisites

- An `ActionPredictionConfig` must exist (create one via `action-prediction-config-create` if needed)
- The project must have sufficient event data (≥500 users, ≥50 positive examples)
- xgboost must be installed (`uv pip install xgboost` if not present)

## Reference scripts

All in `./references/`:

- **`utils.py`** — shared `execute_hogql()` and `fetch_features()` helpers for PostHog API access
- **`query.sql`** — reference HogQL feature query with comments. Adapt per experiment.
- **`train.py`** — fetches training data, trains sklearn Pipeline, saves `model.pkl` + `metrics.json`
- **`predict.py`** — fetches scoring data, loads pipeline, outputs `scores.parquet` + `scores.json`

## Workflow

### Phase 1: Setup

1. If no `ActionPredictionConfig` exists for the target, create one:

   ```text
   action-prediction-config-create(
     name="Predict upgraded_plan",
     event_name="upgraded_plan",   # or action=<id>
     lookback_days=7
   )
   ```

   This auto-triggers a training Task. Note the returned config ID — all models will reference it.

2. Note the returned config ID — all models will reference it.

### Phase 2: Data discovery

Use `execute-sql` with HogQL to understand the project's data before engineering features:

1. **Active users**: `SELECT uniq(person_id) FROM events WHERE timestamp >= now() - interval 90 day`
2. **Top events**: `SELECT event, count() as c FROM events WHERE timestamp >= now() - interval 90 day GROUP BY event ORDER BY c DESC LIMIT 20`
3. **Base rate**: count users who performed the target event vs total eligible users
4. **Person properties**: `read-data-schema` to discover available properties

Report findings to the user before proceeding. This is the one pause point.

**Stop conditions**: If fewer than 50 positive examples, warn. If fewer than 500 users, refuse.

### Phase 3: Feature engineering

Write a HogQL feature query. See `./references/query.sql` for the reference pattern.

The key constraint is **temporal correctness**:

- Training: `T = now() - interval {W} day`, features from `[T-90d, T]`, labels from `(T, T+W]`
- Scoring: `T = now()`, features from `[now()-90d, now()]`, no labels

The agent iterates on this query across experiments — adding features, removing noise, testing different windows. Always add `LIMIT 50000` (HogQL defaults to 100).

### Phase 4: Training

Write a `train.py` script based on `./references/train.py`. The script should:

1. Fetch the training data via `utils.fetch_features()` using the HogQL query
2. Build an sklearn Pipeline (preprocessing + XGBoost + isotonic calibration)
3. Stratified train/test split
4. Evaluate: AUC-ROC (primary), AUC-PR, Brier score
5. Refit on all data, save `model.pkl` + `metrics.json`

Record the model:

```text
action-prediction-model-create(
  config=<config_id>,
  model_url="https://placeholder.s3.amazonaws.com/models/<model_id>.pkl",
  metrics={"auc_roc": 0.72, "auc_pr": 0.19, "brier": 0.08},
  feature_importance={"days_since_last_event": 0.15, ...},
  artifact_scripts={"query": "<HogQL query>", "utils": "<utils.py source>", "train": "<train.py source>", "predict": "<predict.py source>"}
)
```

### Phase 5: Experiment loop (autonomous)

Once the baseline is established, loop autonomously. The single metric is **AUC-ROC on the held-out test set** — higher is better.

```text
LOOP (until stopped or diminishing returns):
  1. Review previous runs — read notes, check what helped, what didn't
  2. Formulate hypothesis: what change might improve AUC-ROC?
  3. Modify the HogQL query and/or training script
  4. Execute train.py (it fetches its own data, records the run)
  5. Compare AUC-ROC to current best:
     → Improved: PATCH config → winning_model = this model
     → Equal or worse: keep the model recorded but don't update winning_model
     → Crash: log in notes, fix if easy, skip if fundamental
  6. Write notes on what you tried and observed
  7. Continue to next experiment
```

**Keep going.** Don't stop after the first improvement. Try to get even better, or see if you can simplify the model without sacrificing performance. If you're stuck, think harder — try combining near-misses, try more radical feature changes, re-examine the data.

**Simplicity criterion**: all else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Removing a feature and getting equal AUC is a win — that's a simpler model. An improvement of ~0 but much simpler code? Keep.

**Experiment ideas** (after baseline):

- Add per-event ratios for top events to the HogQL query
- Hyperparameter sweep: max_depth ∈ {4,6,8}, learning_rate ∈ {0.05,0.1,0.2}
- Feature selection: drop features with importance < 0.01
- Add person properties as features
- Extend observation window from 90d to 180d
- Try different time windows for frequency features (3d, 14d, 60d)
- Interaction features in the query (e.g. downloads per session)

### Phase 6: Model card

After the loop, produce a summary:

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

### Next step: score users

Once a winning model exists, suggest the `predicting-user-actions` skill to score users. It uses the winning model's `artifact_scripts` to fetch fresh data, apply the trained pipeline, and write prediction scores as person properties — making them available in cohorts, feature flags, and experiments.

## Guardrails

- **Single metric**: AUC-ROC on the held-out test set. Higher is better. This is the only number that decides keep vs discard.
- **Simplicity**: all else being equal, simpler is better. Fewer features that achieve the same AUC = better model. Removing complexity for equal performance is a win.
- **No hardcoding**: reference scripts use `downloaded_file` / 28 days as an example — replace with actual target event and lookback_days.
- **Leakage prevention**: features from observation window only; target event excluded from feature columns
- **Calibration**: always isotonic via sklearn Pipeline
- **Features**: aim for 15-40. More than 50 risks overfitting
- **Imbalance**: always use `scale_pos_weight`, never downsample
- **Base rate awareness**: base rate varies by action. Adjust bucket thresholds accordingly. Always report base rate.
- **Lab notebook**: every run must include notes — what was tried, what was observed, what to try next. This is the experiment log.
- **Reproducibility**: seed=42, every run stores query + utils + train + predict in `artifact_scripts`. Fully self-contained.
- **Crash handling**: if sandbox fails, log in notes, try to fix if it's simple (typo, import), skip if the idea is fundamentally broken.
- **HogQL**: do not use `currentTeamId()` (MCP scopes automatically), always add `LIMIT 50000`
- **model_url**: S3 storage path (use `action-prediction-config-upload-url` to get a presigned upload URL and storage path)
