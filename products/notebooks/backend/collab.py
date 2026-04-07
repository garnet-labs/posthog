"""
Collaboration service for notebooks using Redis as the step buffer.

Each notebook has:
- A Redis key `notebook:collab:{notebook_id}:version` holding the current collab version
- A Redis key `notebook:collab:{notebook_id}:steps` holding a list of serialized steps
- A Redis pub/sub channel `notebook:collab:{notebook_id}:events` for broadcasting

Steps are indexed by version: step at index i was applied at version (start_version + i + 1).
The step buffer is transient - it exists only while clients are connected and is used to
reconcile concurrent edits. Postgres holds the authoritative document state.
"""

import json
import time
from dataclasses import dataclass

import structlog

from posthog import redis as posthog_redis

logger = structlog.get_logger(__name__)

STEP_BUFFER_TTL_SECONDS = 3600  # 1 hour - steps expire if no activity
VERSION_KEY_TTL_SECONDS = 3600
CHANNEL_PREFIX = "notebook:collab"


def _version_key(notebook_id: str) -> str:
    return f"{CHANNEL_PREFIX}:{notebook_id}:version"


def _steps_key(notebook_id: str) -> str:
    return f"{CHANNEL_PREFIX}:{notebook_id}:steps"


def _start_version_key(notebook_id: str) -> str:
    return f"{CHANNEL_PREFIX}:{notebook_id}:start_version"


def _channel_key(notebook_id: str) -> str:
    return f"{CHANNEL_PREFIX}:{notebook_id}:events"


@dataclass
class StepSubmissionResult:
    accepted: bool
    version: int  # current version after submission (or current version if rejected)
    steps_since: list[dict] | None = None  # steps the client missed (only on rejection)


def initialize_collab_session(notebook_id: str, version: int) -> int:
    """Initialize or refresh the collaboration session for a notebook.

    Sets the starting version in Redis if not already present.
    Returns the current collab version.
    """
    client = posthog_redis.get_client()
    version_key = _version_key(notebook_id)
    start_version_key = _start_version_key(notebook_id)

    # Use SET NX to avoid overwriting an existing session
    client.set(start_version_key, str(version), ex=VERSION_KEY_TTL_SECONDS, nx=True)
    current = client.get(version_key)
    if current is None:
        client.set(version_key, str(version), ex=VERSION_KEY_TTL_SECONDS)
        return version
    return int(current)


def submit_steps(
    notebook_id: str,
    client_id: str,
    steps_json: list[dict],
    last_seen_version: int,
) -> StepSubmissionResult:
    """Submit editing steps for a notebook.

    Uses a Redis transaction (WATCH/MULTI/EXEC) to ensure atomicity:
    - If last_seen_version matches the current version, steps are accepted
    - Otherwise, the client needs to rebase and resubmit
    """
    client = posthog_redis.get_client()
    version_key = _version_key(notebook_id)
    steps_key = _steps_key(notebook_id)
    start_version_key = _start_version_key(notebook_id)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with client.pipeline() as pipe:
                pipe.watch(version_key)

                current_version_raw = pipe.get(version_key)
                if current_version_raw is None:
                    # Session expired or never initialized - reject so client refreshes
                    return StepSubmissionResult(accepted=False, version=0)

                current_version = int(current_version_raw)

                if last_seen_version != current_version:
                    # Version mismatch - client needs to rebase
                    pipe.unwatch()
                    missed_steps = _get_steps_since(client, notebook_id, last_seen_version)
                    return StepSubmissionResult(
                        accepted=False,
                        version=current_version,
                        steps_since=missed_steps,
                    )

                new_version = current_version + len(steps_json)

                # Atomic: append steps and update version
                pipe.multi()
                for step in steps_json:
                    step_data = json.dumps({"step": step, "client_id": client_id, "version": current_version + 1})
                    pipe.rpush(steps_key, step_data)
                    current_version += 1

                pipe.set(version_key, str(new_version), ex=VERSION_KEY_TTL_SECONDS)
                pipe.expire(steps_key, STEP_BUFFER_TTL_SECONDS)
                pipe.expire(start_version_key, VERSION_KEY_TTL_SECONDS)
                pipe.execute()

            # Publish event outside the transaction
            event = json.dumps(
                {
                    "type": "steps",
                    "client_id": client_id,
                    "version": new_version,
                    "steps": steps_json,
                }
            )
            client.publish(_channel_key(notebook_id), event)

            return StepSubmissionResult(accepted=True, version=new_version)

        except posthog_redis.redis.WatchError:
            # Concurrent modification - retry
            if attempt == max_retries - 1:
                logger.warning("notebook_collab_submit_max_retries", notebook_id=notebook_id)
                current_raw = client.get(version_key)
                current = int(current_raw) if current_raw else 0
                return StepSubmissionResult(accepted=False, version=current)
            continue

    # Should not reach here
    return StepSubmissionResult(accepted=False, version=0)


def get_steps_since(notebook_id: str, since_version: int) -> tuple[int, list[dict]]:
    """Get all steps since a given version.

    Returns (current_version, steps).
    """
    client = posthog_redis.get_client()
    current_raw = client.get(_version_key(notebook_id))
    if current_raw is None:
        return (0, [])

    current_version = int(current_raw)
    if since_version >= current_version:
        return (current_version, [])

    steps = _get_steps_since(client, notebook_id, since_version)
    return (current_version, steps)


def _get_steps_since(client, notebook_id: str, since_version: int) -> list[dict]:
    """Internal helper to fetch steps from Redis list since a version."""
    start_version_raw = client.get(_start_version_key(notebook_id))
    if start_version_raw is None:
        return []

    start_version = int(start_version_raw)
    steps_key = _steps_key(notebook_id)

    # Calculate the index offset
    offset = since_version - start_version
    if offset < 0:
        offset = 0

    raw_steps = client.lrange(steps_key, offset, -1)
    steps = []
    for raw in raw_steps:
        data = json.loads(raw)
        steps.append(data["step"])
    return steps


def subscribe_to_events(notebook_id: str):
    """Create a Redis pub/sub subscription for notebook events.

    Returns a pubsub object that yields messages.
    """
    client = posthog_redis.get_client()
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(_channel_key(notebook_id))
    return pubsub


def publish_presence(notebook_id: str, user_id: str, user_name: str, client_id: str) -> None:
    """Publish a presence heartbeat for a user."""
    client = posthog_redis.get_client()
    event = json.dumps(
        {
            "type": "presence",
            "user_id": user_id,
            "user_name": user_name,
            "client_id": client_id,
            "timestamp": time.time(),
        }
    )
    client.publish(_channel_key(notebook_id), event)
