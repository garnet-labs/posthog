from __future__ import annotations

import pickle
from datetime import UTC, datetime
from typing import Any, cast

from django.db.models import Q

import numpy as np
import structlog
import temporalio.activity
from dateutil.relativedelta import relativedelta

from posthog.schema import IntervalType

from posthog.api.services.query import ExecutionMode
from posthog.caching.calculate_results import calculate_for_query_based_insight
from posthog.models.anomaly import AnomalyScore, InsightAnomalyConfig
from posthog.storage import object_storage
from posthog.sync import database_sync_to_async
from posthog.temporal.anomalies.common import (
    DEFAULT_ANOMALY_DETECTOR_CONFIG,
    INTERVAL_DELTA,
    SPARKLINE_POINTS,
    interval_from_query,
    is_anomalies_enabled_for_team,
    is_time_series_trends_insight,
    min_points_for_scoring,
)
from posthog.temporal.anomalies.trainable_ensemble import FittedEnsemble, TrainableEnsemble
from posthog.temporal.anomalies.types import ScheduleScoringInputs, ScoreInsightActivityInputs, ScoreInsightResult

LOGGER = structlog.get_logger(__name__)


@temporalio.activity.defn
async def fetch_insights_due_for_scoring(inputs: ScheduleScoringInputs) -> list[ScoreInsightActivityInputs]:
    @database_sync_to_async(thread_sensitive=False)
    def _fetch() -> list[ScoreInsightActivityInputs]:
        now = datetime.now(UTC)
        configs = list(
            InsightAnomalyConfig.objects.filter(excluded=False)
            .exclude(model_storage_key="")
            .filter(Q(next_score_due_at__lte=now) | Q(next_score_due_at__isnull=True))
            .select_related("insight__team")
            .order_by("next_score_due_at")[: inputs.batch_size]
        )

        team_flag_cache: dict[int, bool] = {}
        due: list[ScoreInsightActivityInputs] = []
        for config in configs:
            team = config.insight.team
            if team.id not in team_flag_cache:
                team_flag_cache[team.id] = is_anomalies_enabled_for_team(team)
            if not team_flag_cache[team.id]:
                _advance_schedule(config, now)
                continue

            due.append(
                ScoreInsightActivityInputs(
                    insight_id=config.insight_id,
                    team_id=config.insight.team_id,
                    model_storage_key=config.model_storage_key,
                    detector_config=config.detector_config or DEFAULT_ANOMALY_DETECTOR_CONFIG,
                )
            )
        return due

    return await _fetch()


@temporalio.activity.defn
async def score_insight(inputs: ScoreInsightActivityInputs) -> ScoreInsightResult:
    @database_sync_to_async(thread_sensitive=False)
    def _score() -> ScoreInsightResult:
        now = datetime.now(UTC)

        try:
            config = InsightAnomalyConfig.objects.select_related("insight__team").get(insight_id=inputs.insight_id)
        except InsightAnomalyConfig.DoesNotExist:
            return ScoreInsightResult(insight_id=inputs.insight_id, error="Config not found")

        # Load fitted models from S3
        model_data = object_storage.read_bytes(inputs.model_storage_key, missing_ok=True)
        if model_data is None:
            return ScoreInsightResult(insight_id=inputs.insight_id, error="Model not found in S3")

        try:
            series_models: dict[int, bytes] = pickle.loads(model_data)  # noqa: S301
        except Exception:
            return ScoreInsightResult(insight_id=inputs.insight_id, error="Model deserialization failed")

        insight = config.insight
        is_eligible, trends_query = is_time_series_trends_insight(insight)
        if not is_eligible or trends_query is None:
            _advance_schedule(config, now)
            return ScoreInsightResult(insight_id=inputs.insight_id, error="Not eligible")

        detector_config = inputs.detector_config or DEFAULT_ANOMALY_DETECTOR_CONFIG
        interval_str = interval_from_query(trends_query)
        sparkline_size = SPARKLINE_POINTS.get(interval_str, 30)

        # Fetch the minimum of: sparkline points OR scoring preprocessing needs
        # whichever is larger — sparkline is typically larger (30 vs ~7)
        scoring_needs = min_points_for_scoring(detector_config)
        fetch_points = max(sparkline_size, scoring_needs)
        filters_override = _minimal_date_range(trends_query, fetch_points)

        execution_mode = ExecutionMode.RECENT_CACHE_CALCULATE_BLOCKING_IF_STALE
        if trends_query.interval == IntervalType.HOUR:
            execution_mode = ExecutionMode.CALCULATE_BLOCKING_ALWAYS

        calculation_result = calculate_for_query_based_insight(
            insight,
            team=insight.team,
            execution_mode=execution_mode,
            user=None,
            filters_override=filters_override,
        )

        if not calculation_result.result:
            _advance_schedule(config, now)
            return ScoreInsightResult(insight_id=inputs.insight_id, error="No results")

        results = cast(list[dict[str, Any]], calculation_result.result)
        ensemble = TrainableEnsemble(detector_config)

        for series_index, series_result in enumerate(results):
            if series_result.get("compare") or series_result.get("status") is not None:
                continue

            # Skip series we don't have a trained model for
            if series_index not in series_models:
                continue

            data_list = series_result.get("data", [])
            if len(data_list) < 2:
                continue

            data = np.array(data_list, dtype=float)
            dates: list[str] = series_result.get("days") or series_result.get("labels") or []

            # Load the fitted ensemble for this series
            try:
                fitted = FittedEnsemble.deserialize(series_models[series_index])
            except Exception:
                continue

            try:
                result = ensemble.score(data, fitted)
            except Exception:
                continue

            score = result.score if result.score is not None else 0.0
            is_anomalous = result.is_anomaly

            # Build sparkline snapshot
            snap_data = data_list[-sparkline_size:]
            snap_dates = dates[-sparkline_size:] if dates else []
            anomaly_index = len(snap_data) - 1 if is_anomalous else None

            label = series_result.get("label", f"Series {series_index}")
            breakdown_value = series_result.get("breakdown_value", "")
            if breakdown_value and str(breakdown_value) != label:
                full_label = f"{label} - {breakdown_value}"
            else:
                full_label = label

            timestamp_str = dates[-1] if dates else None
            if timestamp_str:
                try:
                    ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    ts = now
            else:
                ts = now

            AnomalyScore.objects.update_or_create(
                team_id=insight.team_id,
                insight=insight,
                series_index=series_index,
                timestamp=ts,
                defaults={
                    "score": score,
                    "is_anomalous": is_anomalous,
                    "series_label": full_label[:400],
                    "interval": interval_str,
                    "data_snapshot": {
                        "data": snap_data,
                        "dates": snap_dates,
                        "anomaly_index": anomaly_index,
                    },
                    "scored_at": now,
                },
            )

        if config.interval != interval_str:
            config.interval = interval_str
        _advance_schedule(config, now)

        return ScoreInsightResult(insight_id=inputs.insight_id, scored=True)

    return await _score()


def _advance_schedule(config: InsightAnomalyConfig, now: datetime) -> None:
    interval_str = config.interval or "day"
    delta = INTERVAL_DELTA.get(interval_str, relativedelta(days=1))
    config.last_scored_at = now
    config.next_score_due_at = now + delta
    config.save(update_fields=["last_scored_at", "next_score_due_at", "interval"])


def _minimal_date_range(query: Any, points_needed: int) -> dict:
    """Compute the tightest date_from that fetches exactly the points we need.

    For scoring, this is typically sparkline_size (30 for daily) which is
    much less than the full training window (90 for daily).
    """
    from posthog.schema import IntervalType as IT

    match query.interval:
        case IT.DAY:
            return {"date_from": f"-{points_needed}d"}
        case IT.WEEK:
            return {"date_from": f"-{points_needed}w"}
        case IT.MONTH:
            return {"date_from": f"-{points_needed}m"}
        case _:
            return {"date_from": f"-{points_needed}h"}
