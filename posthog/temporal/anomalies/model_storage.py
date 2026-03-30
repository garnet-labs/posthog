"""S3 model storage for fitted anomaly detection ensembles.

Uses posthog.storage.object_storage which handles all boto3/config plumbing.
"""

from __future__ import annotations

import structlog

from posthog.storage import object_storage
from posthog.temporal.anomalies.trainable_ensemble import FittedEnsemble

logger = structlog.get_logger(__name__)

S3_PREFIX = "anomaly-models"


def model_key(team_id: int, insight_id: int, version: int) -> str:
    return f"{S3_PREFIX}/{team_id}/{insight_id}/v{version}.pkl"


def save_model(team_id: int, insight_id: int, version: int, fitted: FittedEnsemble) -> str:
    """Serialize and store a fitted ensemble to S3. Returns the storage key."""
    key = model_key(team_id, insight_id, version)
    data = fitted.serialize()
    object_storage.write(key, data)
    logger.info("anomaly_model_saved", key=key, size_bytes=len(data), team_id=team_id, insight_id=insight_id)
    return key


def load_model(key: str) -> FittedEnsemble | None:
    """Load a fitted ensemble from S3. Returns None if not found."""
    data = object_storage.read_bytes(key, missing_ok=True)
    if data is None:
        logger.warning("anomaly_model_not_found", key=key)
        return None
    return FittedEnsemble.deserialize(data)


def delete_model(key: str) -> None:
    """Delete a model from S3."""
    try:
        object_storage.delete(key)
    except Exception:
        logger.warning("anomaly_model_delete_failed", key=key)


def delete_old_versions(team_id: int, insight_id: int, keep_version: int) -> int:
    """Delete model versions older than keep_version. Returns count deleted."""
    prefix = f"{S3_PREFIX}/{team_id}/{insight_id}/"
    keys = object_storage.list_objects(prefix) or []
    deleted = 0
    for key in keys:
        # Parse version from key like "anomaly-models/1/2/v3.pkl"
        try:
            filename = key.split("/")[-1]
            v = int(filename.replace("v", "").replace(".pkl", ""))
            if v < keep_version:
                delete_model(key)
                deleted += 1
        except (ValueError, IndexError):
            continue
    return deleted
