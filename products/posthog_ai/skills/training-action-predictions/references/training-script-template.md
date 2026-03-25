# Training script template

This is the baseline Python training script. The agent writes and iterates on this script across experiments. Each version is stored in the `artifact_script` field of `ActionPredictionModelRun`.

The script expects the feature matrix as a CSV string (from the HogQL feature extraction query) passed via stdin or as a variable.

```python
import json
import sys

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from xgboost import XGBClassifier

SEED = 42
np.random.seed(SEED)


def time_based_split(df, n_folds=3, gap_days=7):
    """Split data into temporal folds with a gap between train and test."""
    df = df.sort_values("days_since_last_event", ascending=False)
    fold_size = len(df) // (n_folds + 1)
    folds = []
    for i in range(n_folds):
        test_start = fold_size * (i + 1)
        test_end = fold_size * (i + 2)
        train_end = test_start - gap_days  # approximate gap via index offset
        if train_end < fold_size:
            continue
        train_idx = df.index[:train_end]
        test_idx = df.index[test_start:test_end]
        folds.append((train_idx, test_idx))
    return folds


def train(csv_data: str) -> dict:
    df = pd.read_csv(pd.io.common.StringIO(csv_data))

    # Separate features and label
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

    # XGBoost with class imbalance handling
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
        # Fallback: simple 70/30 split by index order
        split_idx = int(len(df) * 0.7)
        folds = [(df.index[:split_idx], df.index[split_idx:])]

    cv_metrics = {"auc_roc": [], "auc_pr": [], "brier": []}

    for train_idx, test_idx in folds:
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        model = XGBClassifier(**params)
        model.fit(X_train, y_train)

        # Isotonic calibration
        calibrated = CalibratedClassifierCV(model, method="isotonic", cv="prefit")
        calibrated.fit(X_train, y_train)

        probs = calibrated.predict_proba(X_test)[:, 1]

        cv_metrics["auc_roc"].append(roc_auc_score(y_test, probs))
        cv_metrics["auc_pr"].append(average_precision_score(y_test, probs))
        cv_metrics["brier"].append(brier_score_loss(y_test, probs))

    # Final model on all data
    final_model = XGBClassifier(**params)
    final_model.fit(X, y)

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
    }

    # Signal quality
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
        "params": params,
    }


if __name__ == "__main__":
    csv_data = sys.stdin.read()
    result = train(csv_data)
    print(json.dumps(result, indent=2))
```

## How the agent uses this

1. Run the feature extraction query via `execute-sql` to get a CSV feature matrix.
2. Adapt this script (add/remove features, tweak hyperparameters).
3. Record each experiment as a `prediction-model-run-create` call with:
   - `artifact_script`: the full Python script text
   - `metrics`: the `metrics` dict from the output
   - `feature_importance`: the `feature_importance` dict from the output
   - `is_winning`: `false` initially — set to `true` via `prediction-model-run-partial-update` if it beats the current best

## Iteration targets

| Experiment        | What to change                                            |
| ----------------- | --------------------------------------------------------- |
| Hyperparams       | `max_depth` in {4,6,8}, `learning_rate` in {0.05,0.1,0.2} |
| Feature selection | Drop features with importance < 0.01, verify AUC holds    |
| More features     | Add per-event ratios, session features, person properties |
| Calibration       | Compare isotonic vs sigmoid, optimize Brier score         |
| Longer window     | Extend observation from 90d to 180d                       |
