# Action Predictions

## Action Prediction Config (`system.action_prediction_configs`)

Prediction configs define a target event or action to predict,
along with a lookback window for training data.
Each config can have a winning model once training completes.

### Columns

Column | Type | Nullable | Description
`id` | uuid | NOT NULL | Primary key
`name` | varchar(400) | NOT NULL | Human-readable name
`description` | text | NOT NULL | Purpose of the prediction config
`action_id` | integer | NULL | FK to `system.actions.id` (mutually exclusive with `event_name`)
`event_name` | varchar(400) | NULL | Raw event name to predict (mutually exclusive with `action_id`)
`lookback_days` | integer | NOT NULL | Number of days to look back for training data
`winning_model_id` | uuid | NULL | FK to `system.action_prediction_models.id`
`created_at` | timestamp with tz | NOT NULL | Creation timestamp
`updated_at` | timestamp with tz | NOT NULL | Last update timestamp

### Key Relationships

- **Action**: `action_id` -> `system.actions.id` (optional, mutually exclusive with `event_name`)
- **Winning Model**: `winning_model_id` -> `system.action_prediction_models.id`

### Important Notes

- Exactly one of `action_id` or `event_name` must be set (never both, never neither)
- A config starts with no winning model; one is set after the training experiment loop completes

---

## Action Prediction Model (`system.action_prediction_models`)

Trained prediction models record evaluation metrics, feature importance,
and artifact scripts produced during a training run.

### Columns

Column | Type | Nullable | Description
`id` | uuid | NOT NULL | Primary key
`config_id` | uuid | NOT NULL | FK to `system.action_prediction_configs.id`
`experiment_id` | uuid | NULL | Groups runs from the same agent experiment session
`model_url` | varchar(2000) | NOT NULL | S3 storage path to the serialized model artifact
`metrics` | jsonb | NOT NULL | Evaluation metrics (e.g. accuracy, AUC, F1)
`feature_importance` | jsonb | NOT NULL | Feature importance scores
`artifact_scripts` | jsonb | NOT NULL | Self-contained scripts (keys: query, utils, train, predict)
`notes` | text | NOT NULL | Agent lab notebook observations
`created_at` | timestamp with tz | NOT NULL | Creation timestamp
`updated_at` | timestamp with tz | NOT NULL | Last update timestamp

### Metrics Structure

```json
{
  "accuracy": 0.87,
  "auc": 0.92,
  "f1": 0.85,
  "precision": 0.88,
  "recall": 0.82
}
```

### Feature Importance Structure

```json
{
  "pageview_count_7d": 0.35,
  "session_count_7d": 0.22,
  "days_since_signup": 0.18,
  "unique_pages_visited": 0.15,
  "avg_session_duration": 0.1
}
```

### Key Relationships

- **Config**: `config_id` -> `system.action_prediction_configs.id` (required)

### Important Notes

- Multiple models can exist per config (one per training run)
- The winning model is referenced back from the config's `winning_model_id`
- `artifact_scripts` contains reproducible scripts: `query` (HogQL for feature extraction), `train` (training script), `predict` (scoring script), `utils` (API helpers)

---

## Common Query Patterns

**List all prediction configs:**

```sql
SELECT id, name, event_name, action_id, lookback_days, winning_model_id
FROM system.action_prediction_configs
ORDER BY created_at DESC
LIMIT 20
```

**Find configs for a specific event:**

```sql
SELECT id, name, lookback_days, winning_model_id
FROM system.action_prediction_configs
WHERE event_name = 'downloaded_file'
```

**List models for a config with their metrics:**

```sql
SELECT id, metrics, feature_importance, notes, created_at
FROM system.action_prediction_models
WHERE config_id = 'config-uuid-here'
ORDER BY created_at DESC
```

**Find the best model by AUC across all configs:**

```sql
SELECT
    m.id,
    m.config_id,
    JSONExtractFloat(m.metrics, 'auc') AS auc,
    JSONExtractFloat(m.metrics, 'f1') AS f1,
    m.created_at
FROM system.action_prediction_models AS m
ORDER BY auc DESC
LIMIT 10
```
