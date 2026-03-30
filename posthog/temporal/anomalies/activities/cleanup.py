from __future__ import annotations

import structlog
import temporalio.activity

from posthog.models.anomaly import AnomalyScore
from posthog.sync import database_sync_to_async
from posthog.temporal.anomalies.types import CleanupScoresActivityInputs

LOGGER = structlog.get_logger(__name__)


@temporalio.activity.defn
async def cleanup_anomaly_scores(inputs: CleanupScoresActivityInputs) -> int:
    @database_sync_to_async(thread_sensitive=False)
    def _cleanup() -> int:
        return AnomalyScore.clean_up_old_scores()

    count = await _cleanup()
    await LOGGER.ainfo("anomaly_scores_cleanup", deleted=count)
    return count
