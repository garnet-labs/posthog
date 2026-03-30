"""Shared helpers for anomaly detection activities."""

from __future__ import annotations

from typing import Any

import posthoganalytics
from dateutil.relativedelta import relativedelta

from posthog.schema import IntervalType, TrendsQuery

from posthog.models.insight import Insight
from posthog.schema_migrations.upgrade_manager import upgrade_query
from posthog.tasks.alerts.utils import NON_TIME_SERIES_DISPLAY_TYPES, WRAPPER_NODE_KINDS
from posthog.utils import get_from_dict_or_attr

FEATURE_FLAG_KEY = "anomalies-tab"

DEFAULT_PREPROCESSING = {"diffs_n": 1, "lags_n": 5}

DEFAULT_ANOMALY_DETECTOR_CONFIG: dict[str, Any] = {
    "type": "ensemble",
    "operator": "or",
    "threshold": 0.95,
    "detectors": [
        {"type": "zscore", "threshold": 0.95, "preprocessing": DEFAULT_PREPROCESSING},
        {
            "type": "knn",
            "threshold": 0.95,
            "n_neighbors": 5,
            "method": "largest",
            "preprocessing": DEFAULT_PREPROCESSING,
        },
        {"type": "pca", "threshold": 0.95, "preprocessing": DEFAULT_PREPROCESSING},
    ],
}

SPARKLINE_POINTS: dict[str, int] = {
    "hour": 48,
    "day": 30,
    "week": 12,
    "month": 12,
}

INTERVAL_DELTA: dict[str, relativedelta] = {
    "hour": relativedelta(hours=1),
    "day": relativedelta(days=1),
    "week": relativedelta(weeks=1),
    "month": relativedelta(months=1),
}

# How often to retrain models per insight interval
RETRAIN_CADENCE: dict[str, relativedelta] = {
    "hour": relativedelta(days=1),
    "day": relativedelta(weeks=1),
    "week": relativedelta(weeks=4),
    "month": relativedelta(months=3),
}


def min_points_for_scoring(detector_config: dict[str, Any]) -> int:
    """Compute the minimum data points needed to score 1 new point.

    For scoring (not training), we only need enough points for preprocessing
    to produce 1 valid output. With diffs_n=1 and lags_n=5, preprocessing
    consumes 6 points, so we need 7 points total (6 consumed + 1 scored).

    We take the max across all sub-detectors in the ensemble.
    """
    sub_detectors = detector_config.get("detectors", [detector_config])
    max_needed = 2  # absolute minimum: 1 point + 1 for context

    for sub in sub_detectors:
        preprocessing = sub.get("preprocessing", {})
        diffs_n = preprocessing.get("diffs_n", 0)
        lags_n = preprocessing.get("lags_n", 0)
        # diffs consumes diffs_n points, lags consumes lags_n points
        # plus 1 for the actual point to score
        needed = 1 + diffs_n + lags_n
        max_needed = max(max_needed, needed)

    return max_needed


def interval_from_query(query: TrendsQuery) -> str:
    match query.interval:
        case IntervalType.HOUR:
            return "hour"
        case IntervalType.WEEK:
            return "week"
        case IntervalType.MONTH:
            return "month"
        case _:
            return "day"


def is_time_series_trends_insight(insight: Insight) -> tuple[bool, TrendsQuery | None]:
    """Check if an insight is a time-series TrendsQuery."""
    if insight.query is None:
        return False, None

    with upgrade_query(insight):
        query = insight.query

    kind = get_from_dict_or_attr(query, "kind")
    if kind in [k.value if hasattr(k, "value") else k for k in WRAPPER_NODE_KINDS]:
        query = get_from_dict_or_attr(query, "source")
        kind = get_from_dict_or_attr(query, "kind")

    if kind != "TrendsQuery":
        return False, None

    try:
        trends_query = TrendsQuery.model_validate(query)
    except Exception:
        return False, None

    display = trends_query.trendsFilter.display if trends_query.trendsFilter else None
    if display in NON_TIME_SERIES_DISPLAY_TYPES:
        return False, None

    return True, trends_query


def is_anomalies_enabled_for_team(team: Any) -> bool:
    return posthoganalytics.feature_enabled(
        FEATURE_FLAG_KEY,
        str(team.uuid),
        groups={"organization": str(team.organization_id), "project": str(team.id)},
        group_properties={
            "organization": {"id": str(team.organization_id)},
            "project": {"id": str(team.id)},
        },
        only_evaluate_locally=True,
        send_feature_flag_events=False,
    )
