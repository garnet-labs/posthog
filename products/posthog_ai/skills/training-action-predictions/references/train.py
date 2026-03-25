"""
train.py — Fetch training data and train a prediction model.

Runs the training query via PostHog API, trains an sklearn Pipeline,
evaluates on a held-out test set, and saves the model + metrics.

Inputs:
    POSTHOG_HOST, POSTHOG_API_KEY, POSTHOG_PROJECT_ID (env vars)
    TRAINING_QUERY (inline — the agent adapts this per experiment)

Outputs:
    model.pkl    — pickled sklearn Pipeline
    metrics.json — evaluation metrics and feature importance

The agent adapts this script per experiment: change the query, swap model,
tune hyperparams, change preprocessing steps, etc.
"""

import os
import json
import pickle

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from utils import fetch_features
from xgboost import XGBClassifier

# ── Config ──────────────────────────────────────────────────────────────────

MODEL_PATH = os.environ.get("MODEL_PATH", "/tmp/model.pkl")
METRICS_PATH = os.environ.get("METRICS_PATH", "/tmp/metrics.json")
DATA_PATH = "/tmp/train_data.parquet"

SEED = 42
TEST_FRACTION = 0.25
MAX_USERS = int(os.environ.get("MAX_USERS", "10000"))

# ── Training query ────────────────────────────────────────────────────────────
# IMPORTANT: The agent MUST adapt this query per experiment:
# - Replace 'downloaded_file' with the actual target event name
# - Replace '28' with the actual lookback_days from the ActionPredictionModel
# - Replace '118' in the WHERE clause with lookback + observation (e.g. 28 + 90)
# - Add/remove feature columns as the experiment evolves
# The query below is a REFERENCE for the 'downloaded_file' / 28-day example.
TRAINING_QUERY = """
SELECT
    person_id,
    countIf(event = 'downloaded_file'
        AND timestamp > now() - interval 28 day) > 0 AS label,
    dateDiff('day',
        maxIf(timestamp, timestamp <= now() - interval 28 day),
        now() - interval 28 day) AS days_since_last_event,
    dateDiff('day',
        maxIf(timestamp, event = 'downloaded_file' AND timestamp <= now() - interval 28 day),
        now() - interval 28 day) AS days_since_last_target,
    countIf(timestamp <= now() - interval 28 day) AS events_total,
    countIf(timestamp > now() - interval 58 day
        AND timestamp <= now() - interval 28 day) AS events_30d,
    countIf(timestamp > now() - interval 35 day
        AND timestamp <= now() - interval 28 day) AS events_7d,
    countIf(event = 'downloaded_file'
        AND timestamp <= now() - interval 28 day) AS target_action_count,
    uniqIf(event, timestamp <= now() - interval 28 day) AS unique_event_types,
    countIf(timestamp > now() - interval 43 day
        AND timestamp <= now() - interval 28 day)
    / greatest(countIf(timestamp > now() - interval 58 day
        AND timestamp <= now() - interval 43 day), 1) AS trend_ratio_15d,
    countIf(event = '$pageview' AND timestamp <= now() - interval 28 day)
        / greatest(countIf(timestamp <= now() - interval 28 day), 1) AS pageview_ratio,
    countIf(event = '$autocapture' AND timestamp <= now() - interval 28 day)
        / greatest(countIf(timestamp <= now() - interval 28 day), 1) AS autocapture_ratio
FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 118 day
  AND timestamp <= now()
GROUP BY person_id
HAVING events_total >= 5
LIMIT 50000
"""


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    np.random.seed(SEED)

    # ── Fetch data ───────────────────────────────────────────────────────
    print("Fetching training data...")
    df = fetch_features(TRAINING_QUERY, DATA_PATH)

    # ── Validate ─────────────────────────────────────────────────────────
    assert "person_id" in df.columns, "Missing person_id column"
    assert "label" in df.columns, "Missing label column"

    feature_cols = [c for c in df.columns if c not in {"person_id", "label"}]
    print(f"Features ({len(feature_cols)}): {feature_cols}")

    # ── Sample if needed ─────────────────────────────────────────────────
    if len(df) > MAX_USERS:
        print(f"Sampling {MAX_USERS} from {len(df)} users")
        pos = df[df["label"] == 1]
        neg = df[df["label"] == 0]
        n_pos = min(len(pos), MAX_USERS)
        n_neg = min(len(neg), MAX_USERS - n_pos)
        df = pd.concat(
            [
                pos.sample(n=n_pos, random_state=SEED),
                neg.sample(n=n_neg, random_state=SEED),
            ]
        ).reset_index(drop=True)

    X = df[feature_cols]
    y = df["label"].values

    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    print(f"Users: {len(y)} ({n_pos} positive, {n_neg} negative, base rate {n_pos / len(y):.4f})")

    # ── Split ────────────────────────────────────────────────────────────
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=TEST_FRACTION, random_state=SEED)
    train_idx, test_idx = next(splitter.split(X, y))

    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    print(f"Train: {len(y_train)} ({int(y_train.sum())} positive)")
    print(f"Test:  {len(y_test)} ({int(y_test.sum())} positive)")

    # ── Build pipeline ───────────────────────────────────────────────────
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="constant", fill_value=0), feature_cols),
        ],
        remainder="drop",
    )

    xgb = XGBClassifier(
        objective="binary:logistic",
        eval_metric="auc",
        max_depth=6,
        learning_rate=0.1,
        n_estimators=200,
        scale_pos_weight=n_neg / max(n_pos, 1),
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=SEED,
        verbosity=0,
    )

    pipeline = Pipeline(
        [
            ("preprocessor", preprocessor),
            ("model", CalibratedClassifierCV(xgb, method="isotonic", cv=3)),
        ]
    )

    # ── Train ────────────────────────────────────────────────────────────
    print("Training...")
    pipeline.fit(X_train, y_train)

    # ── Evaluate ─────────────────────────────────────────────────────────
    probs = pipeline.predict_proba(X_test)[:, 1]

    auc_roc = roc_auc_score(y_test, probs)
    auc_pr = average_precision_score(y_test, probs)
    brier = brier_score_loss(y_test, probs)

    print(f"\nTest metrics:")
    print(f"  AUC-ROC: {auc_roc:.4f}")
    print(f"  AUC-PR:  {auc_pr:.4f}")
    print(f"  Brier:   {brier:.4f}")

    # ── Refit on all data ────────────────────────────────────────────────
    print("Refitting on all data...")
    pipeline.fit(X, y)

    # ── Feature importance ───────────────────────────────────────────────
    # CalibratedClassifierCV(cv=3) trains internal copies, so .estimator
    # isn't fitted. Extract importance from the first calibrated estimator.
    calibrated_model = pipeline.named_steps["model"]
    base_model = calibrated_model.calibrated_classifiers_[0].estimator
    importances = base_model.feature_importances_
    feature_importance = {
        feature_cols[i]: round(float(importances[i]), 4) for i in np.argsort(importances)[::-1] if importances[i] > 0
    }

    signal_quality = "green" if auc_roc >= 0.75 else "yellow" if auc_roc >= 0.65 else "red"

    # ── Save ─────────────────────────────────────────────────────────────
    artifact = {
        "pipeline": pipeline,
        "feature_cols": feature_cols,
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(artifact, f)
    print(f"\nModel saved to {MODEL_PATH}")

    metrics = {
        "auc_roc": round(float(auc_roc), 4),
        "auc_pr": round(float(auc_pr), 4),
        "brier": round(float(brier), 4),
        "n_train": len(y_train),
        "n_test": len(y_test),
        "n_positive": n_pos,
        "base_rate": round(n_pos / len(y), 4),
        "signal_quality": signal_quality,
    }
    result = {"metrics": metrics, "feature_importance": feature_importance}

    with open(METRICS_PATH, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Metrics saved to {METRICS_PATH}")
    print(f"\nSignal quality: {signal_quality}")
    print(f"Top features: {list(feature_importance.items())[:5]}")


if __name__ == "__main__":
    main()
