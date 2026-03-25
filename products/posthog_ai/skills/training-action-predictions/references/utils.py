"""
utils.py — Shared helpers for prediction scripts.

Provides PostHog API access and common utilities used by train.py and predict.py.
"""

import os

import pandas as pd
import requests

# ── Config ──────────────────────────────────────────────────────────────────

POSTHOG_HOST = os.environ.get("POSTHOG_HOST", "http://localhost:8000")
POSTHOG_API_KEY = os.environ.get("POSTHOG_API_KEY", "")
POSTHOG_PROJECT_ID = os.environ.get("POSTHOG_PROJECT_ID", "1")


# ── PostHog API ──────────────────────────────────────────────────────────────


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
