"""
utils.py — Shared helpers for prediction scripts.

Provides PostHog API access and common utilities used by train.py and predict.py.
"""

import os

import pandas as pd
import requests

# ── Config ──────────────────────────────────────────────────────────────────

POSTHOG_HOST = os.environ.get("POSTHOG_HOST", "http://localhost:8010")
POSTHOG_API_KEY = os.environ.get("POSTHOG_API_KEY", "")
POSTHOG_PROJECT_ID = os.environ.get("POSTHOG_PROJECT_ID", "1")
# Project token for capture/batch — different from the personal API key.
# The personal API key is for the query API; the project token is for event ingestion.
POSTHOG_PROJECT_TOKEN = os.environ.get("POSTHOG_PROJECT_TOKEN", "")


# ── Query API ────────────────────────────────────────────────────────────────


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

    df = pd.DataFrame(results, columns=columns)
    print(f"Query returned {len(df)} rows, {len(columns)} columns")
    return df


def fetch_features(query: str, output_path: str) -> pd.DataFrame:
    """Run a HogQL feature query and save results to parquet."""
    df = execute_hogql(query)
    df.to_parquet(output_path, index=False)
    print(f"Saved to {output_path}")
    return df


# ── Model Run API ────────────────────────────────────────────────────────────


def create_model_run(
    prediction_model_id: str,
    *,
    experiment_id: str | None = None,
    metrics: dict | None = None,
    feature_importance: dict | None = None,
    artifact_scripts: dict | None = None,
    model_url: str = "https://placeholder.s3.amazonaws.com/models/latest.pkl",
) -> dict:
    """Record a training run via the PostHog API.

    Returns the created run dict including its ID.
    """
    url = f"{POSTHOG_HOST}/api/environments/{POSTHOG_PROJECT_ID}/action_prediction_model_runs/"
    headers = {"Authorization": f"Bearer {POSTHOG_API_KEY}"}
    payload = {
        "prediction_model": prediction_model_id,
        "model_url": model_url,
        "metrics": metrics or {},
        "feature_importance": feature_importance or {},
        "artifact_scripts": artifact_scripts or {},
    }
    if experiment_id:
        payload["experiment_id"] = experiment_id

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    run = resp.json()
    print(f"Recorded model run: {run['id']}")
    return run


def set_winning_run(prediction_model_id: str, run_id: str) -> dict:
    """Set the winning run on a prediction model via PATCH."""
    url = f"{POSTHOG_HOST}/api/environments/{POSTHOG_PROJECT_ID}/action_prediction_models/{prediction_model_id}/"
    headers = {"Authorization": f"Bearer {POSTHOG_API_KEY}"}
    payload = {"winning_run": run_id}

    resp = requests.patch(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    model = resp.json()
    print(f"Set winning run on model {prediction_model_id} → {run_id}")
    return model


def get_winning_run(prediction_model_id: str) -> dict | None:
    """Fetch the winning run for a prediction model. Returns None if no winning run."""
    # First get the model to find the winning_run ID
    url = f"{POSTHOG_HOST}/api/environments/{POSTHOG_PROJECT_ID}/action_prediction_models/{prediction_model_id}/"
    headers = {"Authorization": f"Bearer {POSTHOG_API_KEY}"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    model = resp.json()

    winning_run_id = model.get("winning_run")
    if not winning_run_id:
        print(f"No winning run set for model {prediction_model_id}")
        return None

    # Fetch the full run
    run_url = f"{POSTHOG_HOST}/api/environments/{POSTHOG_PROJECT_ID}/action_prediction_model_runs/{winning_run_id}/"
    resp = requests.get(run_url, headers=headers, timeout=30)
    resp.raise_for_status()
    run = resp.json()
    print(f"Winning run: {run['id']} (AUC-ROC: {run.get('metrics', {}).get('auc_roc', '?')})")
    return run


# ── Capture API ──────────────────────────────────────────────────────────────

BATCH_SIZE = 500


def capture_batch(events: list[dict]) -> None:
    """Send a batch of events to PostHog via the /batch/ endpoint.

    Each event dict should have: event, distinct_id, properties.
    The $set key in properties updates person properties automatically.

    Example event:
        {
            "event": "$ai_prediction",
            "distinct_id": "user-uuid",
            "properties": {
                "$ai_prediction_model_id": "model-uuid",
                "$ai_prediction_probability": 0.73,
                "$ai_prediction_bucket": "very_likely",
                "$set": {
                    "p_action_downloaded_file": 0.73,
                    "p_action_downloaded_file_bucket": "very_likely",
                }
            }
        }
    """
    url = f"{POSTHOG_HOST}/batch/"
    token = POSTHOG_PROJECT_TOKEN

    if not token:
        print("ERROR: POSTHOG_PROJECT_TOKEN not set. Cannot send events.")
        return

    total = len(events)
    sent = 0

    for i in range(0, total, BATCH_SIZE):
        chunk = events[i : i + BATCH_SIZE]
        batch = []
        for evt in chunk:
            batch.append(
                {
                    "event": evt["event"],
                    "distinct_id": evt["distinct_id"],
                    "properties": evt.get("properties", {}),
                    "type": "capture",
                }
            )

        payload = {
            "api_key": token,
            "batch": batch,
        }

        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        sent += len(chunk)
        print(f"  Sent {sent}/{total} events")

    print(f"Capture complete: {total} events sent")
