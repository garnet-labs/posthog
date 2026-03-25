# Scoring script template

This script scores users using a trained model. It reads the feature matrix from a parquet file, loads the trained model from a pickle file, and outputs scored users with probability and bucket assignments.

The agent adapts the winning run's `artifact_script` for scoring — replacing the training logic with inference. This template shows the structure.

```python
import json
import pickle
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

# Paths — the agent sets these before execution
FEATURES_PATH = "/tmp/scoring_features.parquet"
MODEL_PATH = "/tmp/model.pkl"
SCORES_PATH = "/tmp/scores.parquet"
SCORES_JSON_PATH = "/tmp/scores.json"

BUCKET_THRESHOLDS = {
    "very_likely": 0.7,
    "likely": 0.4,
    "neutral": 0.15,
}


def assign_bucket(prob: float) -> str:
    if prob >= BUCKET_THRESHOLDS["very_likely"]:
        return "very_likely"
    elif prob >= BUCKET_THRESHOLDS["likely"]:
        return "likely"
    elif prob >= BUCKET_THRESHOLDS["neutral"]:
        return "neutral"
    else:
        return "unlikely"


def score(features_path: str, model_path: str) -> dict:
    # Load trained model artifact
    with open(model_path, "rb") as f:
        artifact = pickle.load(f)

    model = artifact["model"]
    training_feature_cols = artifact["feature_cols"]

    # Load scoring features
    df = pd.read_parquet(features_path)

    person_ids = df["person_id"].values
    exclude_cols = {"person_id", "label"}
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    # Verify feature alignment
    if feature_cols != training_feature_cols:
        missing = set(training_feature_cols) - set(feature_cols)
        extra = set(feature_cols) - set(training_feature_cols)
        if missing:
            return {"error": f"Missing features from training: {missing}"}
        # Reorder to match training order, drop extras
        feature_cols = training_feature_cols
        df = df[["person_id"] + feature_cols]

    X = df[feature_cols].fillna(0).values

    # Score
    probs = model.predict_proba(X)[:, 1]
    buckets = [assign_bucket(p) for p in probs]

    # Build scored user list
    scored_users = []
    for i in range(len(person_ids)):
        scored_users.append({
            "person_id": str(person_ids[i]),
            "probability": round(float(probs[i]), 4),
            "bucket": buckets[i],
        })

    scored_users.sort(key=lambda x: x["probability"], reverse=True)

    # Save scores to parquet
    scores_df = pd.DataFrame(scored_users)
    scores_df.to_parquet(SCORES_PATH, index=False)

    # Distribution summary
    bucket_counts = Counter(buckets)
    total = len(buckets)
    distribution = {
        bucket: {
            "count": bucket_counts.get(bucket, 0),
            "pct": round(100 * bucket_counts.get(bucket, 0) / max(total, 1), 1),
        }
        for bucket in ["very_likely", "likely", "neutral", "unlikely"]
    }

    return {
        "total_scored": total,
        "distribution": distribution,
        "top_20": scored_users[:20],
    }


if __name__ == "__main__":
    result = score(FEATURES_PATH, MODEL_PATH)
    print(json.dumps(result, indent=2))
    with open(SCORES_JSON_PATH, "w") as f:
        json.dump(result, f, indent=2)
```

## End-to-end scoring flow

1. **Extract features**: run the scoring query via `execute-sql`, save to parquet
2. **Write script**: write this script (adapted as needed) to a `.py` file
3. **Execute**: run the script — produces scores parquet + JSON summary
4. **Write properties**: iterate over scored users, call `persons-property-set` for each
5. **Create cohorts**: create dynamic cohorts based on bucket thresholds

## Writing person properties

After scoring, the agent writes properties for each user via `persons-property-set`:

```text
persons-property-set(
  person_id="{person_id}",
  properties={"p_action_{name}": 0.73, "p_action_{name}_bucket": "very_likely"}
)
```

## Feature alignment

The scoring script validates that feature columns match the training model. The trained pickle stores `feature_cols` alongside the model, so mismatches are caught before scoring. If columns don't match:

1. Check if the scoring query has the same features as the training query
2. Reorder columns to match training order
3. Drop any extra columns not in the training set
4. Error if required training features are missing
