"""
train.py — Train an XGBoost model on the preprocessed feature matrix.

Inputs:
    train.parquet — training set from preprocess.py
    test.parquet  — test set from preprocess.py

Outputs:
    model.pkl    — pickled model artifact (calibrated model + feature columns + params)
    metrics.json — evaluation metrics and feature importance
"""

import os
import json
import pickle

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from xgboost import XGBClassifier

# ── Config ──────────────────────────────────────────────────────────────────

TRAIN_PATH = os.environ.get("TRAIN_OUTPUT_PATH", "/tmp/train.parquet")
TEST_PATH = os.environ.get("TEST_OUTPUT_PATH", "/tmp/test.parquet")
MODEL_PATH = os.environ.get("MODEL_OUTPUT_PATH", "/tmp/model.pkl")
METRICS_PATH = os.environ.get("METRICS_OUTPUT_PATH", "/tmp/metrics.json")

SEED = 42
np.random.seed(SEED)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    train_df = pd.read_parquet(TRAIN_PATH)
    test_df = pd.read_parquet(TEST_PATH)

    label_col = "label"
    exclude_cols = {"person_id", label_col}
    feature_cols = [c for c in train_df.columns if c not in exclude_cols]

    X_train = train_df[feature_cols].fillna(0).values
    y_train = train_df[label_col].values
    X_test = test_df[feature_cols].fillna(0).values
    y_test = test_df[label_col].values

    n_pos = int(y_train.sum())
    n_neg = int(len(y_train) - n_pos)

    print(f"Training: {len(y_train)} rows ({n_pos} positive)")
    print(f"Test:     {len(y_test)} rows ({int(y_test.sum())} positive)")
    print(f"Features: {len(feature_cols)}")

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

    # Train
    model = XGBClassifier(**params)
    model.fit(X_train, y_train)

    # Calibrate
    calibrated = CalibratedClassifierCV(model, method="isotonic", cv="prefit")
    calibrated.fit(X_train, y_train)

    # Evaluate on test set
    probs = calibrated.predict_proba(X_test)[:, 1]

    if len(np.unique(y_test)) < 2:
        print("ERROR: Test set has only one class. Cannot evaluate.")
        return

    auc_roc = roc_auc_score(y_test, probs)
    auc_pr = average_precision_score(y_test, probs)
    brier = brier_score_loss(y_test, probs)

    print(f"\nTest metrics:")
    print(f"  AUC-ROC: {auc_roc:.4f}")
    print(f"  AUC-PR:  {auc_pr:.4f}")
    print(f"  Brier:   {brier:.4f}")

    # Train final model on all data for deployment
    X_all = np.vstack([X_train, X_test])
    y_all = np.concatenate([y_train, y_test])

    final_model = XGBClassifier(**params)
    final_model.fit(X_all, y_all)

    final_calibrated = CalibratedClassifierCV(final_model, method="isotonic", cv="prefit")
    final_calibrated.fit(X_all, y_all)

    # Feature importance (from final model)
    importances = final_model.feature_importances_
    feature_importance = {
        feature_cols[i]: round(float(importances[i]), 4) for i in np.argsort(importances)[::-1] if importances[i] > 0
    }

    # Signal quality
    signal_quality = "green" if auc_roc >= 0.75 else "yellow" if auc_roc >= 0.65 else "red"

    metrics = {
        "auc_roc": round(float(auc_roc), 4),
        "auc_pr": round(float(auc_pr), 4),
        "brier": round(float(brier), 4),
        "n_train": len(y_train),
        "n_test": len(y_test),
        "n_positive_train": n_pos,
        "n_positive_test": int(y_test.sum()),
        "base_rate": round(n_pos / len(y_train), 4),
        "signal_quality": signal_quality,
    }

    # Save model artifact
    artifact = {
        "model": final_calibrated,
        "feature_cols": feature_cols,
        "params": params,
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(artifact, f)
    print(f"\nModel saved to {MODEL_PATH}")

    # Save metrics
    result = {
        "metrics": metrics,
        "feature_importance": feature_importance,
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Metrics saved to {METRICS_PATH}")
    print(f"\nSignal quality: {signal_quality}")
    print(f"Top features: {list(feature_importance.items())[:5]}")


if __name__ == "__main__":
    main()
