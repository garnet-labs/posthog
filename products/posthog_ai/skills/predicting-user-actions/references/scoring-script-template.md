# Scoring script template

This script scores users using a trained model. It reads the feature matrix from stdin (CSV from HogQL), applies the model, and outputs scored users with probability and bucket assignments.

In practice, the agent adapts the winning run's `artifact_script` for scoring — replacing the training logic with inference. This template shows the structure.

```python
import json
import sys

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

SEED = 42
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


def score(csv_data: str, model_params: dict) -> dict:
    df = pd.read_csv(pd.io.common.StringIO(csv_data))

    person_ids = df["person_id"].values
    exclude_cols = {"person_id", "label"}
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    X = df[feature_cols].fillna(0).values

    # Reconstruct and load the trained model
    # In production this loads from S3 via model_url;
    # during hackathon, retrain on the full training set
    model = XGBClassifier(**model_params)
    # model = load_model_from_artifact(model_url)

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

    # Sort by probability descending
    scored_users.sort(key=lambda x: x["probability"], reverse=True)

    # Distribution summary
    from collections import Counter
    bucket_counts = Counter(buckets)
    total = len(buckets)
    distribution = {
        bucket: {"count": bucket_counts.get(bucket, 0),
                 "pct": round(100 * bucket_counts.get(bucket, 0) / max(total, 1), 1)}
        for bucket in ["very_likely", "likely", "neutral", "unlikely"]
    }

    return {
        "total_scored": total,
        "distribution": distribution,
        "top_20": scored_users[:20],
        "all_scores": scored_users,
    }


if __name__ == "__main__":
    csv_data = sys.stdin.read()
    # Model params should come from the winning run's artifact_script
    params = {}  # populated by the agent from the winning run
    result = score(csv_data, params)
    print(json.dumps(result, indent=2))
```

## Writing person properties

After scoring, the agent writes properties for each user. Two approaches:

### Via `persons-property-set` MCP tool

```text
persons-property-set(
  person_id="{person_id}",
  properties={"p_action_{name}": 0.73, "p_action_{name}_bucket": "very_likely"}
)
```

### Via batch HogQL (if available)

For large-scale scoring, a batch approach is preferred over individual API calls.

## Adapting from the training script

The scoring script is derived from the winning run's `artifact_script`:

1. Remove the training/CV loop
2. Remove label column handling
3. Keep the same feature columns and preprocessing
4. Load the trained model instead of training a new one
5. Add bucket assignment and output formatting
