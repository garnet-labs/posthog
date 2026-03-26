"""
predict.py — Fetch fresh data, score users, and write results back to PostHog.

Runs the scoring query via PostHog API (same features as training, but
T=now() and no label), loads the trained pipeline, scores users, then:
  1. Saves scores locally (parquet + JSON)
  2. Sends $ai_prediction events to PostHog (ClickHouse) for audit trail
  3. Sets person properties ($set) for cohorts/flags/targeting

Inputs:
    POSTHOG_HOST, POSTHOG_API_KEY, POSTHOG_PROJECT_ID, POSTHOG_PROJECT_TOKEN (env vars)
    model.pkl    — trained pipeline from train.py
    SCORING_QUERY (inline — same features as training, different time window)

Outputs:
    scores.parquet — person_id, probability, bucket (local)
    scores.json    — summary with distribution and top 20 (local)
    $ai_prediction events in ClickHouse (remote)
    p_action_{name} person properties (remote)
"""

import os
import json
import pickle
from collections import Counter

import pandas as pd
from utils import capture_batch, fetch_features

# ── Config ──────────────────────────────────────────────────────────────────

MODEL_PATH = os.environ.get("MODEL_PATH", "/tmp/model.pkl")
DATA_PATH = "/tmp/scoring_data.parquet"
SCORES_PARQUET_PATH = os.environ.get("SCORES_PATH", "/tmp/scores.parquet")
SCORES_JSON_PATH = os.environ.get("SCORES_JSON_PATH", "/tmp/scores.json")

# IMPORTANT: The agent MUST set these per experiment.
TARGET_EVENT = "downloaded_file"  # replace with actual target
MODEL_ID = ""  # set to the ActionPredictionModel UUID
RUN_ID = ""  # set to the ActionPredictionModelRun UUID

# Bucket thresholds — the agent should adjust these based on the base rate.
# For rare actions (base rate < 5%), lower thresholds may be more useful.
# For common actions (base rate > 20%), higher thresholds avoid noise.
BUCKET_THRESHOLDS = {"very_likely": 0.7, "likely": 0.4, "neutral": 0.15}

# ── Scoring query ────────────────────────────────────────────────────────────
# IMPORTANT: The agent MUST adapt this query to match the training query.
# - Replace 'downloaded_file' with the actual target event name
# - Same feature columns as training (same names, same order)
# - T = now() instead of now() - interval W day
# - No label column
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


def property_name(target: str) -> str:
    """Generate the person property name from the target event."""
    return f"p_action_{target.replace(' ', '_').lower()}"


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

    # ── Save locally ─────────────────────────────────────────────────────
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

    # ── Write to PostHog ─────────────────────────────────────────────────
    prop_name = property_name(TARGET_EVENT)
    bucket_prop_name = f"{prop_name}_bucket"

    print(f"\nSending {total} prediction events to PostHog...")
    events = []
    for i in range(len(person_ids)):
        prob = round(float(probs[i]), 4)
        bucket = buckets[i]
        events.append(
            {
                "event": "$ai_prediction",
                "distinct_id": str(person_ids[i]),
                "properties": {
                    "$ai_prediction_model_id": MODEL_ID,
                    "$ai_prediction_run_id": RUN_ID,
                    "$ai_prediction_target_event": TARGET_EVENT,
                    "$ai_prediction_probability": prob,
                    "$ai_prediction_bucket": bucket,
                    "$set": {
                        prop_name: prob,
                        bucket_prop_name: bucket,
                    },
                },
            }
        )

    capture_batch(events)

    # ── Report ───────────────────────────────────────────────────────────
    print(f"\nScore Distribution:")
    for bucket in ["very_likely", "likely", "neutral", "unlikely"]:
        d = distribution[bucket]
        print(f"  {bucket:15s}: {d['count']:5d} ({d['pct']}%)")
    print(f"  {'TOTAL':15s}: {total:5d}")

    print(f"\nTop 10:")
    for _, row in scores.head(10).iterrows():
        print(f"  {str(row['person_id'])[:20]:20s}  p={row['probability']:.4f}  ({row['bucket']})")

    print(f"\nLocal: {SCORES_PARQUET_PATH}")
    print(f"Person properties: {prop_name}, {bucket_prop_name}")


if __name__ == "__main__":
    main()
