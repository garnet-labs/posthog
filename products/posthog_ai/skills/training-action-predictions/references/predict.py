"""
predict.py — Score users using a trained model.

Inputs:
    model.pkl — trained model artifact from train.py
    Environment:
        POSTHOG_HOST, POSTHOG_API_KEY, POSTHOG_PROJECT_ID

Outputs:
    scores.parquet — scored users with person_id, probability, bucket
    scores.json   — summary with distribution and top 20

The scoring query mirrors the training feature query but with T=now()
and no label column.
"""

import os
import json
import pickle
from collections import Counter

import pandas as pd
import requests

# ── Config ──────────────────────────────────────────────────────────────────

POSTHOG_HOST = os.environ.get("POSTHOG_HOST", "http://localhost:8000")
POSTHOG_API_KEY = os.environ.get("POSTHOG_API_KEY", "")
POSTHOG_PROJECT_ID = os.environ.get("POSTHOG_PROJECT_ID", "1")

MODEL_PATH = os.environ.get("MODEL_OUTPUT_PATH", "/tmp/model.pkl")
SCORES_PARQUET_PATH = os.environ.get("SCORES_OUTPUT_PATH", "/tmp/scores.parquet")
SCORES_JSON_PATH = os.environ.get("SCORES_JSON_PATH", "/tmp/scores.json")

OBSERVATION_DAYS = 90
MIN_EVENTS = 5

BUCKET_THRESHOLDS = {"very_likely": 0.7, "likely": 0.4, "neutral": 0.15}


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


def execute_hogql(query: str) -> pd.DataFrame:
    """Execute a HogQL query via the PostHog API and return a DataFrame."""
    url = f"{POSTHOG_HOST}/api/projects/{POSTHOG_PROJECT_ID}/query/"
    headers = {"Authorization": f"Bearer {POSTHOG_API_KEY}"}
    payload = {
        "query": {
            "kind": "HogQLQuery",
            "query": query,
        }
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    columns = data["columns"]
    results = data["results"]
    return pd.DataFrame(results, columns=columns)


def build_scoring_query(feature_cols: list[str]) -> str:
    """Build a scoring query that matches training features but with T=now()."""
    # This produces the same feature columns as training but without the label.
    # The agent adapts this per experiment to match the training feature query.
    return f"""
SELECT
    person_id,
    dateDiff('day', max(timestamp), now()) AS days_since_last_event,
    dateDiff('day', maxIf(timestamp, event = 'downloaded_file'), now()) AS days_since_last_target,
    count() AS events_total_{OBSERVATION_DAYS}d,
    countIf(timestamp > now() - interval 30 day) AS events_30d,
    countIf(timestamp > now() - interval 7 day) AS events_7d,
    countIf(event = 'downloaded_file') AS target_action_count,
    uniq(event) AS unique_event_types,
    countIf(timestamp > now() - interval 15 day)
        / greatest(countIf(timestamp > now() - interval 30 day AND timestamp <= now() - interval 15 day), 1) AS trend_ratio_15d,
    countIf(event = '$pageview') / greatest(count(), 1) AS pageview_ratio,
    countIf(event = '$autocapture') / greatest(count(), 1) AS autocapture_ratio
FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval {OBSERVATION_DAYS} day
GROUP BY person_id
HAVING events_total_{OBSERVATION_DAYS}d >= {MIN_EVENTS}
"""


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    # Load model
    with open(MODEL_PATH, "rb") as f:
        artifact = pickle.load(f)

    model = artifact["model"]
    training_feature_cols = artifact["feature_cols"]
    print(f"Loaded model with features: {training_feature_cols}")

    # Fetch scoring features
    print("Running scoring query...")
    query = build_scoring_query(training_feature_cols)
    df = execute_hogql(query)
    print(f"Scored {len(df)} users")

    person_ids = df["person_id"].values
    exclude_cols = {"person_id", "label"}
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    # Validate feature alignment
    missing = set(training_feature_cols) - set(feature_cols)
    if missing:
        print(f"ERROR: Missing features from training: {missing}")
        return

    # Reorder to match training
    df_features = df[training_feature_cols].fillna(0)
    X = df_features.values

    # Score
    probs = model.predict_proba(X)[:, 1]
    buckets = [assign_bucket(p) for p in probs]

    # Build output
    scores = pd.DataFrame(
        {
            "person_id": [str(p) for p in person_ids],
            "probability": [round(float(p), 4) for p in probs],
            "bucket": buckets,
        }
    ).sort_values("probability", ascending=False)

    scores.to_parquet(SCORES_PARQUET_PATH, index=False)

    # Summary
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
