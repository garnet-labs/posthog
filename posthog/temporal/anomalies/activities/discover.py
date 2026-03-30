from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.db.models import Q, Subquery

import structlog
import temporalio.activity

from posthog.models.anomaly import InsightAnomalyConfig
from posthog.models.insight import Insight, InsightViewed
from posthog.sync import database_sync_to_async
from posthog.temporal.anomalies.common import (
    DEFAULT_ANOMALY_DETECTOR_CONFIG,
    interval_from_query,
    is_time_series_trends_insight,
)
from posthog.temporal.anomalies.types import DiscoverInsightsActivityInputs, EligibleInsight

LOGGER = structlog.get_logger(__name__)


@temporalio.activity.defn
async def discover_anomaly_insights(inputs: DiscoverInsightsActivityInputs) -> list[EligibleInsight]:
    @database_sync_to_async(thread_sensitive=False)
    def _discover() -> list[EligibleInsight]:
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=inputs.recently_viewed_days)

        recently_viewed_insight_ids = (
            InsightViewed.objects.filter(last_viewed_at__gte=cutoff).values_list("insight_id", flat=True).distinct()
        )
        existing_config_insight_ids = InsightAnomalyConfig.objects.values_list("insight_id", flat=True)

        candidates = (
            Insight.objects.filter(id__in=Subquery(recently_viewed_insight_ids), deleted=False, query__isnull=False)
            .exclude(id__in=Subquery(existing_config_insight_ids))
            .only("id", "team_id", "query")[: inputs.max_candidates]
        )

        eligible: list[EligibleInsight] = []
        for insight in candidates:
            is_eligible, trends_query = is_time_series_trends_insight(insight)
            if not is_eligible or trends_query is None:
                continue

            interval = interval_from_query(trends_query)
            InsightAnomalyConfig.objects.create(
                team_id=insight.team_id,
                insight=insight,
                interval=interval,
                detector_config=DEFAULT_ANOMALY_DETECTOR_CONFIG,
                next_score_due_at=now,
            )
            eligible.append(EligibleInsight(insight_id=insight.id, team_id=insight.team_id, interval=interval))

        # Clean up configs for deleted insights
        InsightAnomalyConfig.objects.filter(Q(insight__deleted=True) | Q(insight__isnull=True)).delete()

        return eligible

    return await _discover()
