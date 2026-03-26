"""
predict.py — Run 003: Score users for "insight created" prediction.

Loads the trained model, adapts the training query for scoring (T=now, no label),
scores all identified users, and sends $ai_prediction events + person properties.

Usage:
    cd products/posthog_ai/skills/training-action-predictions/runs/003-insight-created
    flox activate -- bash -c "uv pip install xgboost -q && python predict.py"
"""

import os
import re
import sys
import json
import pickle
from collections import Counter
from pathlib import Path

# Auto-load .env from the runs directory
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "references"))
from utils import fetch_features

# ── Config ──────────────────────────────────────────────────────────────────

RUN_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(RUN_DIR, "model.pkl")
SCORES_PATH = os.path.join(RUN_DIR, "scores.json")

TARGET_EVENT = "insight created"
LOOKBACK_DAYS = 14

# Bucket thresholds — adjusted for the training base rate
BUCKET_THRESHOLDS = {"very_likely": 0.5, "likely": 0.25, "neutral": 0.1}


# ── Query adaptation ────────────────────────────────────────────────────────


def training_query_to_scoring(query: str, lookback_days: int) -> str:
    """Transform a training query into a scoring query.

    Removes the label column and shifts the time window from
    T=now()-lookback to T=now() so features reflect current state.
    """
    # Remove the label line(s) — everything between "label" markers
    lines = query.split("\n")
    scoring_lines = []
    for line in lines:
        # Skip lines that compute the label
        if "AS label" in line:
            # Also remove the preceding lines that are part of the label expression
            # Walk back to remove continuation lines
            while scoring_lines and scoring_lines[-1].strip() and not scoring_lines[-1].strip().startswith("--"):
                if (
                    "countIf" in scoring_lines[-1]
                    or "if(" in scoring_lines[-1]
                    or "AND " in scoring_lines[-1]
                    or "OR " in scoring_lines[-1]
                    or "IN (" in scoring_lines[-1]
                ):
                    scoring_lines.pop()
                else:
                    break
            continue
        scoring_lines.append(line)

    query = "\n".join(scoring_lines)

    # Shift time window: replace `now() - interval {lookback} day` with `now()`
    # in feature expressions (but not in WHERE clause's start boundary)
    # The WHERE timestamp >= now() - interval 74 day → now() - interval 60 day
    total_window = 60 + lookback_days
    query = query.replace(f"now() - interval {total_window} day", "now() - interval 60 day")
    # Feature cutoffs: now() - interval 14 day → now()
    query = re.sub(
        rf"now\(\) - interval {lookback_days} day",
        "now()",
        query,
    )

    # Clean up any trailing commas before FROM
    query = re.sub(r",\s*\n\s*\n*\s*FROM", "\nFROM", query)

    return query


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


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    # ── Load model ───────────────────────────────────────────────────────
    print(f"Loading model from {MODEL_PATH}")
    with open(MODEL_PATH, "rb") as f:
        artifact = pickle.load(f)  # noqa: S301

    pipeline = artifact["pipeline"]
    feature_cols = artifact["feature_cols"]
    print(f"Model expects {len(feature_cols)} features: {feature_cols}")

    # ── Build scoring query from training query ──────────────────────────
    query_file = sys.argv[1] if len(sys.argv) > 1 else "query.sql"
    with open(os.path.join(RUN_DIR, query_file)) as f:
        training_query = f.read()

    scoring_query = training_query_to_scoring(training_query, LOOKBACK_DAYS)
    print(f"\nScoring query (adapted from {query_file}):")
    print(scoring_query[:500])
    print("...")

    # ── Fetch scoring data ───────────────────────────────────────────────
    print("\nFetching scoring data from PostHog...")
    df = fetch_features(scoring_query, os.path.join(RUN_DIR, "scoring_data.parquet"))

    assert "person_id" in df.columns, "Missing person_id column"

    # Drop label if it somehow survived the transformation
    if "label" in df.columns:
        df = df.drop(columns=["label"])

    # Validate features match
    available = [c for c in df.columns if c != "person_id"]
    missing = set(feature_cols) - set(available)
    if missing:
        print(f"ERROR: Missing features: {missing}")
        print(f"Available: {available}")
        return

    X = df[feature_cols]
    person_ids = df["person_id"].values
    print(f"Scoring {len(person_ids)} users")

    # ── Score ────────────────────────────────────────────────────────────
    probs = pipeline.predict_proba(X)[:, 1]
    buckets = [assign_bucket(float(p)) for p in probs]

    # ── Summary ──────────────────────────────────────────────────────────
    bucket_counts = Counter(buckets)
    total = len(buckets)
    distribution = {
        bucket: {
            "count": bucket_counts.get(bucket, 0),
            "pct": round(100 * bucket_counts.get(bucket, 0) / max(total, 1), 1),
        }
        for bucket in ["very_likely", "likely", "neutral", "unlikely"]
    }

    print(f"\nScore distribution:")
    for bucket in ["very_likely", "likely", "neutral", "unlikely"]:
        d = distribution[bucket]
        print(f"  {bucket:15s}: {d['count']:5d} ({d['pct']}%)")
    print(f"  {'TOTAL':15s}: {total:5d}")

    summary = {
        "total_scored": total,
        "target_event": TARGET_EVENT,
        "distribution": distribution,
        "top_20": [
            {"person_id": str(person_ids[i]), "probability": round(float(probs[i]), 4), "bucket": buckets[i]}
            for i in sorted(range(len(probs)), key=lambda i: -probs[i])[:20]
        ],
    }
    with open(SCORES_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nScores saved to {SCORES_PATH}")

    # ── Send $ai_prediction events ───────────────────────────────────────
    # Write to POSTHOG_CAPTURE_HOST (local dev) not POSTHOG_HOST (prod).
    # Read from prod, write to local.
    capture_host = os.environ.get("POSTHOG_CAPTURE_HOST", "http://localhost:8010")
    token = os.environ.get("POSTHOG_CAPTURE_TOKEN", "")
    if not token:
        print(f"\nPOSTHOG_CAPTURE_TOKEN not set — skipping event capture to {capture_host}.")
        print("Set it in runs/.env to send predictions.")
        return

    prop_name = f"p_action_{TARGET_EVENT.replace(' ', '_').lower()}"
    bucket_prop = f"{prop_name}_bucket"

    print(f"\nSending {total} $ai_prediction events to {capture_host}...")
    import requests

    sent = 0
    batch_size = 500
    for i in range(0, len(person_ids), batch_size):
        chunk_events = []
        for j in range(i, min(i + batch_size, len(person_ids))):
            prob = round(float(probs[j]), 4)
            chunk_events.append(
                {
                    "event": "$ai_prediction",
                    "distinct_id": str(person_ids[j]),
                    "properties": {
                        "$ai_prediction_target_event": TARGET_EVENT,
                        "$ai_prediction_probability": prob,
                        "$ai_prediction_bucket": buckets[j],
                        "$set": {
                            prop_name: prob,
                            bucket_prop: buckets[j],
                        },
                    },
                    "type": "capture",
                }
            )
        resp = requests.post(
            f"{capture_host}/batch/",
            json={"api_key": token, "batch": chunk_events},
            timeout=60,
        )
        resp.raise_for_status()
        sent += len(chunk_events)
        print(f"  Sent {sent}/{total} events")

    print(f"Person properties: {prop_name}, {bucket_prop}")


if __name__ == "__main__":
    main()
