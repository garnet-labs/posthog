"""
predict.py — Fetch fresh data and score users with a trained pipeline.

Runs the scoring query via PostHog API (same features as training, but
T=now() and no label), loads the trained pipeline, and outputs scores.

Inputs:
    POSTHOG_HOST, POSTHOG_API_KEY, POSTHOG_PROJECT_ID (env vars)
    model.pkl    — trained pipeline from train.py
    SCORING_QUERY (inline — same features as training, different time window)

Outputs:
    scores.parquet — person_id, probability, bucket
    scores.json    — summary with distribution and top 20
"""

import os
import json
import pickle
from collections import Counter

import pandas as pd
from utils import fetch_features

# ── Config ──────────────────────────────────────────────────────────────────

MODEL_PATH = os.environ.get("MODEL_PATH", "/tmp/model.pkl")
DATA_PATH = "/tmp/scoring_data.parquet"
SCORES_PARQUET_PATH = os.environ.get("SCORES_PATH", "/tmp/scores.parquet")
SCORES_JSON_PATH = os.environ.get("SCORES_JSON_PATH", "/tmp/scores.json")

BUCKET_THRESHOLDS = {"very_likely": 0.7, "likely": 0.4, "neutral": 0.15}

# The scoring query mirrors the training query but with T=now() and no label.
# The agent adapts this to match whatever query was used in training.
SCORING_QUERY = """
SELECT
    person_id,
    dateDiff('day', max(timestamp), now()) AS days_since_last_event,
    dateDiff('day',
        maxIf(timestamp, event = 'downloaded_file'),
        now()) AS days_since_last_target,
    count() AS events_total,
    countIf(timestamp > now() - interval 30 day) AS events_30d,
    countIf(timestamp > now() - interval 7 day) AS events_7d,
    countIf(event = 'downloaded_file') AS target_action_count,
    uniq(event) AS unique_event_types,
    countIf(timestamp > now() - interval 15 day)
    / greatest(countIf(timestamp > now() - interval 30 day
        AND timestamp <= now() - interval 15 day), 1) AS trend_ratio_15d,
    countIf(event = '$pageview')
        / greatest(count(), 1) AS pageview_ratio,
    countIf(event = '$autocapture')
        / greatest(count(), 1) AS autocapture_ratio
FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval 90 day
GROUP BY person_id
HAVING events_total >= 5
LIMIT 50000
"""


# ── Helpers ──────────────────────────────────────────────────────────────────


def assign_bucket(prob: float) -> str:
    if prob >= BUCKET_THRESHOLDS["very_likely"]:
        return "very_likely"
    elif prob >= BUCKET_THRESHOLDS["likely"]:
        return "likely"
    elif prob >= BUCKET_THRESHOLDS["neutral"]:
        return "neutral"
    else:
        return "unlikely"


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    # ── Load model ───────────────────────────────────────────────────────
    with open(MODEL_PATH, "rb") as f:
        artifact = pickle.load(f)  # noqa: S301

    pipeline = artifact["pipeline"]
    training_feature_cols = artifact["feature_cols"]
    print(f"Loaded model with {len(training_feature_cols)} features")

    # ── Fetch scoring data ───────────────────────────────────────────────
    print("Fetching scoring data...")
    df = fetch_features(SCORING_QUERY, DATA_PATH)

    assert "person_id" in df.columns, "Missing person_id column"

    # ── Validate features ────────────────────────────────────────────────
    available_cols = [c for c in df.columns if c not in {"person_id", "label"}]
    missing = set(training_feature_cols) - set(available_cols)
    if missing:
        print(f"ERROR: Missing features from training: {missing}")
        return

    X = df[training_feature_cols]
    person_ids = df["person_id"].values

    # ── Score ────────────────────────────────────────────────────────────
    probs = pipeline.predict_proba(X)[:, 1]
    buckets = [assign_bucket(float(p)) for p in probs]

    # ── Output ───────────────────────────────────────────────────────────
    scores = pd.DataFrame(
        {
            "person_id": [str(p) for p in person_ids],
            "probability": [round(float(p), 4) for p in probs],
            "bucket": buckets,
        }
    ).sort_values("probability", ascending=False)

    scores.to_parquet(SCORES_PARQUET_PATH, index=False)

    bucket_counts = Counter(buckets)
    total = len(buckets)
    distribution = {
        bucket: {
            "count": bucket_counts.get(bucket, 0),
            "pct": round(100 * bucket_counts.get(bucket, 0) / max(total, 1), 1),
        }
        for bucket in ["very_likely", "likely", "neutral", "unlikely"]
    }

    summary = {
        "total_scored": total,
        "distribution": distribution,
        "top_20": scores.head(20).to_dict(orient="records"),
    }

    with open(SCORES_JSON_PATH, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nScore Distribution:")
    for bucket in ["very_likely", "likely", "neutral", "unlikely"]:
        d = distribution[bucket]
        print(f"  {bucket:15s}: {d['count']:5d} ({d['pct']}%)")
    print(f"  {'TOTAL':15s}: {total:5d}")

    print(f"\nTop 10:")
    for _, row in scores.head(10).iterrows():
        print(f"  {str(row['person_id'])[:20]:20s}  p={row['probability']:.4f}  ({row['bucket']})")

    print(f"\nSaved to {SCORES_PARQUET_PATH}")


if __name__ == "__main__":
    main()
