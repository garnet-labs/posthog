"""
train.py — Run 006: Predict "team member invited" on PostHog prod (project 2).

Target: P(identified user invites a team member within 14 days)
Population: all identified users with ≥5 events
Data source: us.posthog.com project 2

Usage:
    cd products/posthog_ai/skills/training-action-predictions/runs/006-team-member-invited
    flox activate -- bash -c "uv pip install xgboost -q && python train.py [query_file]"
"""

import os
import sys
import json
import pickle
from pathlib import Path

# Auto-load .env from the runs directory
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

# Add references dir to path for utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "references"))
from utils import fetch_features

# ── Config ──────────────────────────────────────────────────────────────────

RUN_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(RUN_DIR, "model.pkl")
METRICS_PATH = os.path.join(RUN_DIR, "metrics.json")
DATA_PATH = os.path.join(RUN_DIR, "train_data.parquet")

SEED = 42
TEST_FRACTION = 0.25

# Negative-to-positive ratio for balanced sampling.
# 1.0 = 50/50, 5.0 = 5x negatives per positive (~17% positive rate).
# The agent should tune this — lower ratios help the model learn rare patterns,
# higher ratios give more realistic probability calibration.
NEG_RATIO = float(os.environ.get("NEG_RATIO", "5.0"))

# ── Training query ──────────────────────────────────────────────────────────
# Pass a query file as argv[1] to override, e.g.: python train.py query_v2_simple.sql

query_file = sys.argv[1] if len(sys.argv) > 1 else "query.sql"
query_path = os.path.join(RUN_DIR, query_file)
print(f"Using query: {query_file}")
with open(query_path) as f:
    TRAINING_QUERY = f.read()


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    np.random.seed(SEED)

    # ── Fetch data ───────────────────────────────────────────────────────
    print("Fetching training data from PostHog...")
    print(f"  Host: {os.environ.get('POSTHOG_HOST', 'NOT SET')}")
    print(f"  Project: {os.environ.get('POSTHOG_PROJECT_ID', 'NOT SET')}")
    df = fetch_features(TRAINING_QUERY, DATA_PATH)

    # ── Validate ─────────────────────────────────────────────────────────
    assert "person_id" in df.columns, "Missing person_id column"
    assert "label" in df.columns, "Missing label column"

    feature_cols = [c for c in df.columns if c not in {"person_id", "label"}]
    print(f"Features ({len(feature_cols)}): {feature_cols}")

    # ── Balanced sampling ──────────────────────────────────────────────
    pos = df[df["label"] == 1]
    neg = df[df["label"] == 0]
    n_pos = len(pos)
    n_neg_sample = min(len(neg), max(int(n_pos * NEG_RATIO), 500))
    print(f"Raw data: {n_pos} positive, {len(neg)} negative")
    df = pd.concat(
        [
            pos,
            neg.sample(n=n_neg_sample, random_state=SEED),
        ]
    ).reset_index(drop=True)
    print(f"Balanced sample: {n_pos} positive, {n_neg_sample} negative (ratio 1:{NEG_RATIO:.0f})")

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
        "n_negative": n_neg,
        "neg_ratio": NEG_RATIO,
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
