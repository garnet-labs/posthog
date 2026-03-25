# Training script template

This is the baseline Python training script. The agent writes and iterates on this script across experiments. Each version is stored in the `artifact_script` field of `ActionPredictionModelRun`.

The script reads the feature matrix from a parquet file, trains an XGBoost model, saves the trained model as a pickle file, and outputs metrics as JSON.

```python
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from xgboost import XGBClassifier

SEED = 42
np.random.seed(SEED)

# Paths — the agent sets these before execution
FEATURES_PATH = "/tmp/features.parquet"
MODEL_PATH = "/tmp/model.pkl"
METRICS_PATH = "/tmp/metrics.json"


def time_based_split(df, n_folds=3, gap_days=7):
    """Split data into temporal folds with a gap between train and test."""
    df = df.sort_values("days_since_last_event", ascending=False)
    fold_size = len(df) // (n_folds + 1)
    folds = []
    for i in range(n_folds):
        test_start = fold_size * (i + 1)
        test_end = fold_size * (i + 2)
        train_end = test_start - gap_days
        if train_end < fold_size:
            continue
        train_idx = df.index[:train_end]
        test_idx = df.index[test_start:test_end]
        folds.append((train_idx, test_idx))
    return folds


def train(features_path: str) -> dict:
    df = pd.read_parquet(features_path)

    label_col = "label"
    exclude_cols = {"person_id", label_col}
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    X = df[feature_cols].fillna(0).values
    y = df[label_col].values

    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)

    if n_pos < 50:
        return {"error": f"Too few positive examples ({n_pos}). Need at least 50."}
    if len(y) < 500:
        return {"error": f"Too few users ({len(y)}). Need at least 500."}

    params = {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "max_depth": 6,
        "learning_rate": 0.1,
        "n_estimators": 200,
        "scale_pos_weight": n_neg / max(n_pos, 1),
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "random_state": SEED,
        "verbosity": 0,
    }

    # Time-based cross-validation
    folds = time_based_split(df, n_folds=3, gap_days=7)
    if not folds:
        split_idx = int(len(df) * 0.7)
        folds = [(df.index[:split_idx], df.index[split_idx:])]

    cv_metrics = {"auc_roc": [], "auc_pr": [], "brier": []}

    for train_idx, test_idx in folds:
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        if len(np.unique(y_test)) < 2:
            continue

        model = XGBClassifier(**params)
        model.fit(X_train, y_train)

        calibrated = CalibratedClassifierCV(model, method="isotonic", cv="prefit")
        calibrated.fit(X_train, y_train)

        probs = calibrated.predict_proba(X_test)[:, 1]

        cv_metrics["auc_roc"].append(roc_auc_score(y_test, probs))
        cv_metrics["auc_pr"].append(average_precision_score(y_test, probs))
        cv_metrics["brier"].append(brier_score_loss(y_test, probs))

    if not cv_metrics["auc_roc"]:
        return {"error": "No valid CV folds — not enough temporal variation."}

    # Final model on all data
    final_model = XGBClassifier(**params)
    final_model.fit(X, y)

    # Calibrated final model for scoring
    calibrated_final = CalibratedClassifierCV(final_model, method="isotonic", cv="prefit")
    calibrated_final.fit(X, y)

    # Save model + metadata
    artifact = {
        "model": calibrated_final,
        "feature_cols": feature_cols,
        "params": params,
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(artifact, f)

    # Feature importance
    importances = final_model.feature_importances_
    feature_importance = {
        feature_cols[i]: round(float(importances[i]), 4)
        for i in np.argsort(importances)[::-1]
        if importances[i] > 0
    }

    metrics = {
        "auc_roc": round(float(np.mean(cv_metrics["auc_roc"])), 4),
        "auc_pr": round(float(np.mean(cv_metrics["auc_pr"])), 4),
        "brier": round(float(np.mean(cv_metrics["brier"])), 4),
        "n_users": len(y),
        "n_positive": n_pos,
        "base_rate": round(n_pos / len(y), 4),
        "n_folds": len(cv_metrics["auc_roc"]),
    }

    auc = metrics["auc_roc"]
    if auc >= 0.75:
        metrics["signal_quality"] = "green"
    elif auc >= 0.65:
        metrics["signal_quality"] = "yellow"
    else:
        metrics["signal_quality"] = "red"

    return {
        "metrics": metrics,
        "feature_importance": feature_importance,
        "model_path": MODEL_PATH,
    }


if __name__ == "__main__":
    result = train(FEATURES_PATH)
    print(json.dumps(result, indent=2))
    with open(METRICS_PATH, "w") as f:
        json.dump(result, f, indent=2)
```

## How the agent uses this

1. Run the feature extraction query via `execute-sql`.
2. Save results to a parquet file at `FEATURES_PATH`.
3. Write this script (adapted as needed) to a `.py` file.
4. Execute the script — it produces:
   - A pickle file at `MODEL_PATH` containing the calibrated model + feature column names
   - A JSON file at `METRICS_PATH` with evaluation results
   - JSON output to stdout
5. Record the experiment as a `prediction-model-run-create` call with:
   - `artifact_script`: the full Python script text
   - `metrics`: the `metrics` dict from the output
   - `feature_importance`: the `feature_importance` dict from the output
   - `is_winning`: `true` if this run beats the current best AUC-ROC, `false` otherwise
   - `model_url`: a valid `https://` URL (e.g. `https://placeholder.s3.amazonaws.com/models/<run_id>.pkl`)

## Iteration targets

| Experiment        | What to change                                            |
| ----------------- | --------------------------------------------------------- |
| Hyperparams       | `max_depth` in {4,6,8}, `learning_rate` in {0.05,0.1,0.2} |
| Feature selection | Drop features with importance < 0.01, verify AUC holds    |
| More features     | Add per-event ratios, person properties                   |
| Calibration       | Compare isotonic vs sigmoid, optimize Brier score         |
| Longer window     | Extend observation from 90d to 180d                       |
