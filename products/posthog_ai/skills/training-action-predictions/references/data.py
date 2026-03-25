"""
data.py — Fetch feature matrix from PostHog via HogQL.

Inputs:
    Environment:
        POSTHOG_HOST       — PostHog API base URL (e.g. http://localhost:8000)
        POSTHOG_API_KEY    — PostHog personal API key
        POSTHOG_PROJECT_ID — Project/team ID

    Config (set by agent per experiment):
        TARGET_EVENT  — event name to predict (e.g. 'downloaded_file')
        LOOKBACK_DAYS — prediction window in days (e.g. 28)

Outputs:
    data.parquet — raw feature matrix with columns:
        person_id, label, days_since_last_event, days_since_last_target,
        events_total_90d, events_30d, events_7d, target_action_count,
        unique_event_types, trend_ratio_15d, pageview_ratio, ...
"""

import os
import sys

import pandas as pd
import requests

# ── Config ──────────────────────────────────────────────────────────────────

POSTHOG_HOST = os.environ.get("POSTHOG_HOST", "http://localhost:8000")
POSTHOG_API_KEY = os.environ.get("POSTHOG_API_KEY", "")
POSTHOG_PROJECT_ID = os.environ.get("POSTHOG_PROJECT_ID", "1")

TARGET_EVENT = "downloaded_file"
LOOKBACK_DAYS = 28
OBSERVATION_DAYS = 90
MIN_EVENTS = 5
MAX_USERS = int(os.environ.get("MAX_USERS", "10000"))

OUTPUT_PATH = os.environ.get("DATA_OUTPUT_PATH", "/tmp/data.parquet")


# ── HogQL query ─────────────────────────────────────────────────────────────


def build_feature_query(target: str, lookback: int, observation: int, min_events: int) -> str:
    """Build the HogQL feature extraction query with temporal correctness."""
    return f"""
SELECT
    person_id,

    -- Label: did they perform the target action in the label window?
    countIf(event = '{target}'
        AND timestamp > now() - interval {lookback} day
    ) > 0 AS label,

    -- Recency
    dateDiff('day',
        maxIf(timestamp, timestamp <= now() - interval {lookback} day),
        now() - interval {lookback} day
    ) AS days_since_last_event,

    dateDiff('day',
        maxIf(timestamp, event = '{target}' AND timestamp <= now() - interval {lookback} day),
        now() - interval {lookback} day
    ) AS days_since_last_target,

    -- Frequency (multiple windows)
    countIf(timestamp <= now() - interval {lookback} day) AS events_total_{observation}d,
    countIf(timestamp > now() - interval {lookback + 30} day
        AND timestamp <= now() - interval {lookback} day) AS events_30d,
    countIf(timestamp > now() - interval {lookback + 7} day
        AND timestamp <= now() - interval {lookback} day) AS events_7d,

    -- Target history (excluding label window)
    countIf(event = '{target}'
        AND timestamp <= now() - interval {lookback} day) AS target_action_count,

    -- Event diversity
    uniqIf(event, timestamp <= now() - interval {lookback} day) AS unique_event_types,

    -- Trend: last 15d vs prior 15d (relative to observation cutoff)
    countIf(timestamp > now() - interval {lookback + 15} day
        AND timestamp <= now() - interval {lookback} day)
    / greatest(
        countIf(timestamp > now() - interval {lookback + 30} day
            AND timestamp <= now() - interval {lookback + 15} day),
        1
    ) AS trend_ratio_15d,

    -- Common event ratios
    countIf(event = '$pageview' AND timestamp <= now() - interval {lookback} day)
        / greatest(countIf(timestamp <= now() - interval {lookback} day), 1) AS pageview_ratio,
    countIf(event = '$autocapture' AND timestamp <= now() - interval {lookback} day)
        / greatest(countIf(timestamp <= now() - interval {lookback} day), 1) AS autocapture_ratio

FROM events
WHERE person_id IS NOT NULL
  AND timestamp >= now() - interval {lookback + observation} day
  AND timestamp <= now()
GROUP BY person_id
HAVING events_total_{observation}d >= {min_events}
LIMIT 50000
"""


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


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"Target: {TARGET_EVENT}, Lookback: {LOOKBACK_DAYS}d, Observation: {OBSERVATION_DAYS}d")

    query = build_feature_query(TARGET_EVENT, LOOKBACK_DAYS, OBSERVATION_DAYS, MIN_EVENTS)
    print("Running HogQL query...")
    df = execute_hogql(query)

    pos = int(df["label"].sum())
    neg = len(df) - pos
    print(f"Rows: {len(df)}, Positive: {pos}, Negative: {neg}, Base rate: {pos / max(len(df), 1):.4f}")

    if pos < 50:
        print(f"WARNING: Only {pos} positive examples. Need at least 50 for reliable training.")
    if len(df) < 500:
        print(f"ERROR: Only {len(df)} users. Need at least 500. Aborting.")
        sys.exit(1)

    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
