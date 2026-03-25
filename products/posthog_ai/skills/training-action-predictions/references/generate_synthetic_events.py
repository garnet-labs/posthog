"""
generate_synthetic_events.py — Inject synthetic events for harder prediction targets.

Creates 'contacted_support' events with a non-trivial probability model:
- Base probability depends on a noisy combination of user behavior
- Users with high file activity BUT low session diversity are more likely
- Recent signups (< 30 days) have higher probability
- Some pure randomness to prevent perfect prediction

This gives the agent a harder target that requires real feature iteration
to get good AUC (expect 0.65-0.80 with good features, not 0.95+).

Usage:
    export POSTHOG_HOST=http://localhost:8010
    export POSTHOG_API_KEY=<personal_api_key>
    export POSTHOG_PROJECT_ID=1
    export POSTHOG_PROJECT_TOKEN=<project_token>
    flox activate -- python generate_synthetic_events.py
"""

import os
import sys
import random
from datetime import UTC, datetime, timedelta

import numpy as np
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import POSTHOG_HOST, POSTHOG_PROJECT_TOKEN, execute_hogql

SEED = 123
random.seed(SEED)
np.random.seed(SEED)

# ── Config ──────────────────────────────────────────────────────────────────

# Target base rate: ~8-12% of users contact support
TARGET_BASE_RATE = 0.10
# Noise level: higher = harder to predict (0 = deterministic, 1 = pure random)
NOISE_LEVEL = 0.4
# How many days back events can be placed
EVENT_WINDOW_DAYS = 60


def fetch_user_features() -> list[dict]:
    """Fetch behavioral features for all active users."""
    df = execute_hogql("""
SELECT
    person_id,
    argMax(distinct_id, timestamp) AS distinct_id,
    count() AS total_events,
    countIf(event = 'uploaded_file') AS uploads,
    countIf(event = 'downloaded_file') AS downloads,
    countIf(event = 'shared_file_link') AS shares,
    countIf(event = '$pageview') AS pageviews,
    uniq(event) AS unique_event_types,
    dateDiff('day', min(timestamp), now()) AS account_age_days,
    countIf(timestamp > now() - interval 7 day) AS events_7d,
    countIf(timestamp > now() - interval 30 day) AS events_30d
FROM events
WHERE person_id IS NOT NULL
  AND event NOT IN ('$ai_prediction', '$ai_prediction_test', 'contacted_support')
  AND timestamp >= now() - interval 120 day
GROUP BY person_id
HAVING total_events >= 3
LIMIT 50000
""")
    return df.to_dict(orient="records")


def compute_support_probability(user: dict) -> float:
    """Compute probability of contacting support based on behavioral signals.

    The model is intentionally non-trivial:
    - High file activity (uploads + downloads) increases probability
    - But high event diversity DECREASES it (power users figure things out)
    - New accounts (< 30 days) are more likely to contact support
    - Low recent activity (events_7d) relative to older activity suggests frustration
    - Noise makes it imperfect
    """
    # Normalize features to 0-1 range (approximate)
    file_activity = min((user["uploads"] + user["downloads"]) / 50, 1.0)
    diversity = min(user["unique_event_types"] / 10, 1.0)
    is_new = 1.0 if user["account_age_days"] < 30 else 0.0
    recent_drop = 1.0 if user["events_30d"] > 10 and user["events_7d"] < 3 else 0.0

    # Combine signals with weights
    signal = (
        0.3 * file_activity  # more file activity → more likely
        - 0.2 * diversity  # more diverse usage → less likely (power users)
        + 0.25 * is_new  # new users → more likely
        + 0.15 * recent_drop  # activity drop → frustration → more likely
    )

    # Add noise
    noise = np.random.normal(0, NOISE_LEVEL)
    raw_prob = signal + noise

    # Sigmoid to bound between 0 and 1
    prob = 1 / (1 + np.exp(-3 * (raw_prob - 0.1)))

    # Scale to hit target base rate (approximate)
    return float(np.clip(prob * TARGET_BASE_RATE * 3, 0.01, 0.5))


def generate_support_events(users: list[dict]) -> list[dict]:
    """Generate contacted_support events based on computed probabilities."""
    events = []
    contacted = 0

    for user in users:
        prob = compute_support_probability(user)

        if random.random() < prob:
            contacted += 1
            # Place event randomly within the last EVENT_WINDOW_DAYS
            days_ago = random.randint(0, EVENT_WINDOW_DAYS)
            hours_ago = random.randint(0, 23)
            ts = datetime.now(tz=UTC) - timedelta(days=days_ago, hours=hours_ago)

            # Vary the support reason
            reasons = ["billing_question", "bug_report", "feature_request", "account_issue", "performance"]
            reason = random.choice(reasons)
            severity = random.choices(["low", "medium", "high"], weights=[0.5, 0.35, 0.15])[0]

            events.append(
                {
                    "event": "contacted_support",
                    "distinct_id": str(user["distinct_id"]),
                    "timestamp": ts.isoformat(),
                    "properties": {
                        "reason": reason,
                        "severity": severity,
                        "response_time_hours": round(random.uniform(0.5, 72), 1),
                    },
                    "type": "capture",
                }
            )

    print(f"Generated {contacted} contacted_support events from {len(users)} users")
    print(f"Actual base rate: {contacted / len(users):.4f}")
    return events


def send_events(events: list[dict]) -> None:
    """Send events via the batch API."""
    url = f"{POSTHOG_HOST}/batch/"
    token = POSTHOG_PROJECT_TOKEN
    batch_size = 500

    if not token:
        print("ERROR: POSTHOG_PROJECT_TOKEN not set")
        return

    total = len(events)
    sent = 0

    for i in range(0, total, batch_size):
        chunk = events[i : i + batch_size]
        payload = {
            "api_key": token,
            "batch": chunk,
        }
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        sent += len(chunk)
        print(f"  Sent {sent}/{total}")

    print(f"Done: {total} events sent")


def main() -> None:
    print("Fetching user features...")
    users = fetch_user_features()
    print(f"Found {len(users)} active users")

    print("\nGenerating contacted_support events...")
    events = generate_support_events(users)

    if events:
        print(f"\nSending {len(events)} events to PostHog...")
        send_events(events)
    else:
        print("No events generated!")


if __name__ == "__main__":
    main()
