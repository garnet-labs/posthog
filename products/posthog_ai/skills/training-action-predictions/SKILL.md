---
name: training-action-predictions
description: 'Train a predictive model for user actions using an autonomous experiment loop. Checks for existing models and prior research first, then explores project data via HogQL, engineers features, trains XGBoost models with iterative refinement, and records results. Use when the user asks to predict an action, train a prediction model, build a propensity score, or predict conversion/churn/upgrade.'
---

# Training action predictions

Build a model that predicts P(user performs action X within W days). Also supports constructed labels like churn (absence of events) and lifecycle predictions (relative to each user's signup time). Uses an autonomous experiment loop — explore data, write a HogQL feature query, train an sklearn Pipeline, evaluate, iterate.

All feature engineering is pushed down to ClickHouse via HogQL. The query returns `person_id, label, features` — Python just trains the model.

## Critical decisions (make these during EDA, before writing queries)

### 1. Population: who do you train on?

The population determines what you're predicting. Get this wrong and the model is useless regardless of AUC.

**Filter to real/identified users.** Most projects have a mix of anonymous traffic (bots, one-time visitors, server-side events) and real users. Training on everyone dilutes the base rate and teaches the model noise. During EDA, find the right filter — it varies by project:

- A person property like `email IS NOT NULL`, `is_signed_up`, or `is_identified`
- A behavioral filter like "had at least N events of type X"
- A cohort or segment the customer defines

**Adoption vs continuation.** Are you predicting _new behavior_ (user hasn't done X before) or _repeat behavior_ (user who does X will do it again)? Both are valid but they're different models:

- **Adoption**: exclude users who already exhibit the target behavior. Useful for: feature discovery, onboarding optimization, expansion to new product areas
- **Continuation**: include everyone. Useful for: predicting repeat purchases, expansion (more invites), ongoing engagement
- Document which one the model is in the model card. If `prior_target_count` dominates feature importance, it's a continuation model — note this explicitly.

**Lifecycle stage filtering.** For activation predictions, restrict to users at a specific lifecycle stage (e.g. signed up in last 30 days). Use per-user time anchoring (see below) so features reflect each user's actual stage, not a fixed global window.

### 2. Label design: what exactly are you predicting?

The target can be:

- **A simple named event**: `event = 'X'` — cleanest, no subquery needed
- **An action (autocapture + selectors/URL)**: needs `IN` subquery to isolate the expensive `elements_chain LIKE` or `$current_url LIKE` scan to the narrow label window. Never put LIKE scans in the main aggregation.
- **A constructed/virtual label**: absence of events (`countIf(...) = 0` for churn), threshold-based (`countIf(...) >= N`), or any HogQL expression. The framework handles these naturally.

### 3. Time anchoring: fixed window or per-user?

- **Fixed window** (default): `T = now() - interval W day`, features from `[T-obs, T]`, labels from `(T, T+W]`. Simple, works for general predictions.
- **Per-user anchoring**: for lifecycle predictions, compute features relative to each user's anchor event (signup, first purchase, etc.). `INNER JOIN (SELECT person_id, min(timestamp) AS anchor_time ...)` then use `anchor_time + interval N day` in all filters. This gives more training data and matches production scoring exactly.

### 4. Sampling strategy

Base rate determines the approach:

- **> 3%**: natural `LIMIT` sampling works. Python balanced sampling (NEG_RATIO) handles the rest.
- **0.1% - 3%**: use `ORDER BY label DESC, rand()` in HogQL so all positives come first. Set LIMIT high enough to capture all positives + negatives.
- **< 0.1%**: very rare — widen the label window, filter to a more relevant population, or accept that the model will have high variance.

In train.py, use configurable `NEG_RATIO` (default 5.0 = ~17% positive rate). 50/50 is too aggressive and double-compensates with `scale_pos_weight`. The isotonic calibration adjusts probabilities back to the true base rate.

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

### Phase 1: Setup and prior research

1. If no `ActionPredictionConfig` exists for the target, create one:

   ```text
   action-prediction-config-create(
     name="Predict upgraded_plan",
     event_name="upgraded_plan",   # or action=<id>
     lookback_days=7
   )
   ```

   This auto-triggers a training Task. Note the returned config ID — all models will reference it.

2. **Check for existing models**: list models for this config via `action-prediction-model-list` with `?config={config_id}`. This determines whether you're in **first experiment** or **improvement** mode.

3. **If models exist** — load prior research before doing anything else:
   - Retrieve the config to find the `winning_model` (if set)
   - Retrieve the winning model (or the model with the best `metrics.auc_roc`) and read:
     - `notes` — what was tried, what worked, what didn't
     - `artifact_scripts` — the query, utils, train, and predict scripts that produced the best result so far
     - `metrics` — the current best AUC-ROC to beat
     - `feature_importance` — which features matter most
   - Also load `notes` from the 3-5 most recent models (not just the winner) to understand the full experiment history — what hypotheses were tested, which failed, which showed promise
   - **Start from the winning model's scripts**, not from the reference scripts. Adapt and improve from the best known state

4. **If no models exist** — this is a fresh start. You'll use the reference scripts as your starting point and do comprehensive data discovery in Phase 2.

### Phase 2: Data discovery

The depth of EDA depends on whether prior models exist:

#### First experiment (no prior models) — comprehensive discovery

Explore the project's data thoroughly. The goals are: validate feasibility, **choose the right population**, and discover project-specific feature candidates.

1. **Population analysis** (do this FIRST):
   - Total users vs identified/real users — find the filter that separates real users from noise. Check person properties (`email`, `is_signed_up`, `is_identified`) and activity patterns. What % of users are anonymous?
   - For the target action: who does it? Are they power users, new users, a specific segment? This determines the training population.
   - Decide: adoption (exclude existing target users) or continuation (include everyone)?

2. **Base rate among the right population**: count users who performed the target event vs total eligible users _after_ applying the population filter. The base rate among all users is often misleadingly low.

3. **Active users**: `SELECT uniq(person_id) FROM events WHERE timestamp >= now() - interval 90 day`

4. **Top events**: `SELECT event, count() as c FROM events WHERE timestamp >= now() - interval 90 day GROUP BY event ORDER BY c DESC LIMIT 30` — pay special attention to custom events (not `$pageview`, `$autocapture`). These are the project's domain language.

5. **Event properties**: for key events, explore what properties they carry: `SELECT event, arrayJoin(JSONExtractKeys(properties)) as key, count() as c FROM events WHERE event = 'X' GROUP BY event, key ORDER BY c DESC LIMIT 20`

6. **Person properties**: `read-data-schema` to discover available person properties. Note: person properties in GROUP BY queries require `any()` wrapper. `toFloatOrDefault` needs `0.0` not `0` as the default value. Person properties from server-side events are often null — extract metadata from event properties (e.g. `$pageview` properties for device/OS/geo) instead.

7. **Correlations with target**: which events co-occur most with the target? This identifies _candidates_ but **high EDA correlation does not guarantee model importance**. Population-level rate differences (2-3x baseline) often don't improve AUC because they're confounded with general activity level. The experiment loop is the real test — don't skip iterations based on EDA alone.

Report findings to the user before proceeding. This is the one pause point. Highlight the population design decision and which features you plan to try.

**Stop conditions**: If fewer than 50 positive examples after population filtering, warn (widen the label window or relax the population). If fewer than 500 users in the population, refuse.

#### Improvement mode (prior models exist) — targeted discovery

Skip the broad exploration. Instead:

1. Review the prior research (notes from recent models) — what's already been tried?
2. **Check online performance** (if predictions have been running — see "Online performance validation" below). This is the gold standard: how did the model's predictions actually perform against reality?
3. Identify gaps: what features or approaches haven't been explored yet?
4. Formulate 2-3 specific hypotheses to test based on what prior experiments and online performance suggest
5. If prior notes mention promising directions that weren't fully explored, start there
6. Only do targeted EDA for specific hypotheses (e.g. "check if `payment_failed` events exist" before adding payment features)

### Phase 3: Feature engineering

Write a HogQL feature query.

- **First experiment**: base it on `./references/query.sql`, incorporating findings from the comprehensive EDA
- **Improvement mode**: start from the winning model's `artifact_scripts.query` and modify based on your hypotheses

#### Two tiers of features

Every query should include both **generic features** and **project-specific features**. This distinction is the core of our approach.

**Generic features** (the baseline — every project gets these):

- Recency: days since last event, days since last target event
- Frequency: total events, events in 7d/30d/90d windows
- Target history: how many times the user has done the target action before
- Event diversity: unique event types
- Trends: recent activity vs prior period ratios
- Standard event ratios: `$pageview`, `$autocapture`, `$pageleave` as share of total

These are in the reference query and provide a reasonable baseline. But they're the same for every project — they can't capture what makes _this_ project's users different.

**Project-specific features** (the uplift — this is where agents shine):

- **Custom event counts/ratios**: if the project sends `subscription_renewed`, `api_key_created`, `report_exported`, `team_member_invited` — these are domain signals that no generic model would know about. Count them, ratio them, check recency of each
- **Event property features**: if `$pageview` carries a `page` property, or a custom event has `plan_type` or `error_code` — use `countIf(event = 'X' AND properties.$Y = 'Z')` to create granular features
- **Person property features**: if the project has `industry`, `company_size`, `signup_source`, `plan` as person properties — include them directly. These are often strong static predictors
- **Behavioral sequences**: did the user do A then B? How many sessions included event X? Time between first and last occurrence of a key event
- **Domain-specific ratios**: e.g. `support_tickets / days_active`, `features_used / features_available`, `api_calls / dashboard_views`

The bet is that **project-specific features are where the real predictive power lives**. Generic recency/frequency features get you to AUC 0.6-0.7 for most targets. The custom features — informed by what the agent discovers about this specific project — are what push it to 0.8+.

**Important caveats from real-world testing:**

- **Behavioral features (what users DID) consistently beat metadata (who they ARE)**. Device type, geography, signup method, org properties — these add < 0.01 AUC in most cases. Prioritize event-based features.
- **EDA correlation ≠ model importance.** A feature with 3x activation rate in EDA may add zero AUC because it's confounded with general activity level. XGBoost already captures the underlying signal from simpler features. Always validate via the experiment loop.
- **Person properties are often weak predictors.** Static attributes (company size, plan) rarely help for behavioral predictions. If you include them, use `any()` wrapper in GROUP BY and `toFloatOrDefault(toString(any(person.properties.X)), 0.0)` for numeric conversion.
- **Start lean, add only if AUC improves.** Don't aim for a specific feature count. 5-8 strong features often beat 20+ weak ones. Run the simplified model early — if dropping features improves or matches AUC, the baseline is near the signal ceiling.

#### Leakage risks with custom features

Custom features are powerful but the leakage surface area is much larger than generic features. **If a new feature pushes AUC suspiciously high, assume leakage until proven otherwise.** Common traps:

**Semantic leakage** — the feature is the label in disguise:

- Target is `contacted_support` and you add `countIf(event = 'support_ticket_created')` — this may be the same action or a directly coupled event. Ask: "could this event happen _without_ the target also happening?" If not, it's leaking
- Target is `upgraded_plan` and you add `person.properties.plan` — if the plan property gets set _when_ the upgrade happens, it's a future leak in training (the property reflects post-action state). Check when/how the property gets set
- Target is `churned` and you add `countIf(event = 'subscription_cancelled')` — effectively the same thing

**Temporal leakage** — the feature uses data from after the observation cutoff:

- Person properties are tricky: they reflect the _current_ state, not the state at time T. A property like `last_login_date` or `total_purchases` may include activity from the label window. If in doubt, derive the feature from events with explicit timestamp filters instead of using person properties directly
- Be especially careful with properties that are set by the target action itself (e.g. `$set` in the event that defines the target)

**Causal leakage** — the feature is caused by the target, not a predictor of it:

- Events that happen _because_ the user performed the target action (e.g. `confirmation_email_sent` after `purchased_plan`)
- Properties or events that are downstream effects rather than upstream signals

**How to check**: for any custom feature that seems very predictive (importance > 0.3 or AUC jumps by > 0.1):

1. **Think about the causal graph**: does this event/property cause the target, predict it, or result from it?
2. **Check temporal ordering**: can this event/property exist before the target happens?
3. **Sanity check the AUC**: if AUC goes from 0.65 to 0.95 from one feature, that's almost certainly leakage. Real predictive signal is more modest
4. **Ablation test**: remove the suspicious feature and see if AUC drops back to baseline. If one feature accounts for most of the AUC, investigate it

**When in doubt, leave it out.** A model with AUC 0.72 and no leakage is far more valuable than one with AUC 0.95 that won't generalize to production. Note the leakage analysis in the model's `notes` — document why you included or excluded borderline features.

#### Temporal correctness

The key constraint:

- Training: `T = now() - interval {W} day`, features from `[T-90d, T]`, labels from `(T, T+W]`
- Scoring: `T = now()`, features from `[now()-90d, now()]`, no labels

The agent iterates on this query across experiments — adding features, removing noise, testing different windows. Always add `LIMIT 50000` (HogQL defaults to 100).

**Important**: set `T` at least 7 days in the past (e.g. `T = now() - interval 7 day` for a 7-day lookback) so that the label window `(T, T+W]` is fully in the past. This lets the trained model be used for scoring immediately — if `T` is too recent, the label window extends into the future and the model can't produce valid predictions yet.

### Phase 4: Training

Write a `train.py` script.

- **First experiment**: base it on `./references/train.py`
- **Improvement mode**: start from the winning model's `artifact_scripts.train` and modify

The script should:

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

#### Mandatory: `artifact_scripts`

**Every model MUST include `artifact_scripts` when recorded.** Without these scripts, the model cannot be used for scoring and the entire training effort is wasted. The scoring pipeline (`predicting-user-actions` skill) reads `artifact_scripts` from the winning model to run predictions — if they are missing, predictions cannot run.

The `artifact_scripts` dict MUST contain these four keys:

| Key       | Contents                                        | Why it's needed                                                                                             |
| --------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `query`   | The exact HogQL feature query used for training | Scoring adapts this query to `T=now()` to fetch fresh features with the same columns                        |
| `utils`   | Full source of `utils.py`                       | Shared helpers (`execute_hogql`, `fetch_features`, `capture_batch`) needed by both train and predict        |
| `train`   | Full source of `train.py`                       | Reproducibility — anyone can re-run training from this script alone                                         |
| `predict` | Full source of `predict.py`                     | The scoring script that loads the model, fetches features, scores users, and writes results back to PostHog |

**How to populate**: read the current script sources and include the training query inline:

```python
import os
scripts_dir = os.path.dirname(os.path.abspath(__file__))
artifact_scripts = {}
for name in ("utils", "train", "predict"):
    path = os.path.join(scripts_dir, f"{name}.py")
    if os.path.exists(path):
        with open(path) as f:
            artifact_scripts[name] = f.read()
artifact_scripts["query"] = TRAINING_QUERY
```

**Do not skip this step.** If you record a model without `artifact_scripts`, the model is effectively useless — it has metrics and feature importance for analysis, but cannot produce predictions.

### Phase 5: Experiment loop (autonomous)

Once the baseline is established (or the first iteration on an existing model is done), loop autonomously. The single metric is **AUC-ROC on the held-out test set** — higher is better.

```text
LOOP (until stopped or diminishing returns):
  1. Review previous models — read notes, check what helped, what didn't
  2. Formulate hypothesis: what change might improve AUC-ROC?
  3. Modify the HogQL query and/or training script
  4. Execute train.py (it fetches its own data, records the model)
  5. Compare AUC-ROC to current best:
     → Improved: PATCH config → winning_model = this model
     → Equal or worse: keep the model recorded but don't update winning_model
     → Crash: log in notes, fix if easy, skip if fundamental
  6. Write notes on what you tried and observed
  7. Continue to next experiment
```

**Keep going.** Don't stop after the first improvement. Try to get even better, or see if you can simplify the model without sacrificing performance. If you're stuck, think harder — try combining near-misses, try more radical feature changes, re-examine the data.

**Simplicity criterion**: all else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Removing a feature and getting equal AUC is a win — that's a simpler model. An improvement of ~0 but much simpler code? Keep.

**Experiment ideas** (prioritized):

Simplification (try early — often the biggest win):

- Drop features with importance < 0.03 and re-run. If AUC matches or improves, keep the simpler model
- When signal is concentrated in a few features, extra features add noise

Project-specific features:

- Add counts/ratios for the project's custom events discovered during EDA
- Add event property features (e.g. `countIf(event = 'X' AND properties.$Y = 'Z')`)
- Build domain-specific ratios (e.g. `support_tickets / days_active`)
- Extract metadata from event properties when person properties are null (e.g. device type from `$pageview`)

Temporal patterns (especially for churn/retention):

- Weekly activity buckets: `countIf(... AND timestamp > T-7d AND timestamp <= T)` for each of 8 weeks
- Decay ratios: recent weeks / earlier weeks — captures "fading out" vs "suddenly stopped"
- `weeks_active` count — how many of N weeks had any activity (consistency signal)
- When a dominant recency feature is legitimate, combine it with decay features rather than ablating

Population and window experiments:

- Try different population filters (activity thresholds, lifecycle stages)
- Try per-user time anchoring for lifecycle targets
- Try different label windows (7d, 14d, 30d) — wider windows help rare events
- Try day-3 or day-7 scoring windows for early intervention models

Model tuning (lowest expected uplift — do last):

- Hyperparameter sweep: max_depth ∈ {4,6,8}, learning_rate ∈ {0.05,0.1,0.2}
- Feature selection: drop features with importance < 0.01

### Phase 6: Online performance validation

Once a model has been scoring users in production (via the `predicting-user-actions` skill or scheduled scoring), its predictions are stored as `$ai_prediction` events in ClickHouse. This is the **gold standard** for evaluating model quality — offline AUC on a held-out test set is a proxy, but online performance tells you if the model actually works in the real world.

**When to check**: in improvement mode, if predictions have been running for at least as long as the `lookback_days` window (so outcomes are observable), check online performance before starting new experiments. This should inform what to work on.

**How to check** (via `execute-sql`):

```sql
-- Compare predictions to actual outcomes
-- Join $ai_prediction events with whether the user actually performed the target
SELECT
    p.properties.$ai_prediction_bucket AS predicted_bucket,
    count() AS n_users,
    countIf(actual.did_action = 1) AS n_actually_did,
    countIf(actual.did_action = 1) / count() AS actual_rate
FROM events p
LEFT JOIN (
    SELECT
        person_id,
        1 AS did_action
    FROM events
    WHERE event = '{target_event}'
      AND timestamp > p.timestamp
      AND timestamp <= p.timestamp + interval {lookback_days} day
    GROUP BY person_id
) actual ON p.person_id = actual.person_id
WHERE p.event = '$ai_prediction'
  AND p.properties.$ai_prediction_config_id = '{config_id}'
  AND p.timestamp >= now() - interval {lookback_days * 2} day
  AND p.timestamp <= now() - interval {lookback_days} day
GROUP BY predicted_bucket
ORDER BY actual_rate DESC
```

**What to look for**:

- **Calibration**: does `very_likely` actually have a much higher actual rate than `unlikely`? If the buckets don't separate well, the model isn't working in production regardless of offline AUC
- **Drift**: if online performance is much worse than offline AUC, something has changed — the data distribution may have shifted, or there may be leakage in the training setup that doesn't apply in production
- **Surprising patterns**: which users did the model get wrong? Are there systematic blind spots (e.g. new users always misclassified)?

**How it informs experiments**:

- If online performance matches offline AUC → the model is working, focus on marginal improvements
- If online performance is much worse → likely leakage or drift. Investigate which features behave differently in production vs training. This is more important than adding new features
- If certain buckets are miscalibrated → the model may need recalibration or the bucket thresholds need adjusting
- If the model misses a specific user segment → explore features that distinguish that segment

Include online performance findings in the model card and in experiment notes.

### Phase 7: Model card

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

- **Population first**: decide who to train on before writing features. Filter to identified/real users. Decide adoption vs continuation. Document the population in the model card.
- **Single metric**: AUC-ROC on the held-out test set. Higher is better. But if test set has < 100 positives, note that AUC variance is high.
- **Leakage vigilance**: if AUC > 0.90 on a real-world target, assume leakage until proven otherwise. Check for: (a) upstream-step features from the same user journey, (b) population contamination (existing users making prediction trivial), (c) one feature with importance > 0.3. Run ablation tests on suspicious features.
- **Simplicity**: start lean. Try dropping weak features early — fewer features often match or beat more. Don't aim for a feature count target.
- **Imbalance**: use balanced sampling (NEG_RATIO) + `scale_pos_weight` + isotonic calibration. For rare events (< 0.5% base rate), use `ORDER BY label DESC, rand()` in HogQL.
- **Base rate awareness**: base rate varies by action AND by population. Always report both the population definition and the base rate within it.
- **Model card must include**: target, population, adoption-vs-continuation label, AUC-ROC, base rate, top features, what was tried.
- **Lab notebook**: every model must include notes — what was tried, what was observed, what to try next. Future sessions read these as prior research.
- **Reproducibility**: seed=42, every run MUST store query + utils + train + predict in `artifact_scripts`. Without these, the model cannot be scored.
- **HogQL patterns**:
  - Do not use `currentTeamId()` (MCP scopes automatically)
  - Always add `LIMIT 50000`
  - For action-based targets (autocapture + selectors), use `IN` subquery for the label to isolate expensive `elements_chain LIKE` scans
  - Person properties in GROUP BY need `any()` wrapper
  - `toFloatOrDefault` needs `0.0` not `0` as default
  - For per-user time anchoring: `INNER JOIN (SELECT person_id, min(timestamp) AS anchor ...)` with `GROUP BY person_id, anchor`
- **model_url**: S3 storage path (use `action-prediction-config-upload-url` to get a presigned upload URL and storage path)
