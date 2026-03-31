"""Tests for posthog/temporal/anomalies/common.py"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from unittest.mock import MagicMock, patch

from parameterized import parameterized

from posthog.schema import ChartDisplayType, EventsNode, IntervalType, TrendsQuery

from posthog.temporal.anomalies.common import interval_from_query, is_time_series_trends_insight, min_points_for_scoring

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def _noop_upgrade_query(_insight):
    """Drop-in replacement for upgrade_query that does nothing."""
    yield


def _trends_query(
    interval: IntervalType = IntervalType.DAY,
    display: ChartDisplayType | None = None,
) -> TrendsQuery:
    from posthog.schema import TrendsFilter

    trends_filter = TrendsFilter(display=display) if display is not None else None
    return TrendsQuery(interval=interval, trendsFilter=trends_filter, series=[EventsNode()])


def _mock_insight(query: dict | None) -> MagicMock:
    """Create a mock Insight with the given query dict."""
    insight = MagicMock()
    insight.query = query
    return insight


# ---------------------------------------------------------------------------
# min_points_for_scoring
# ---------------------------------------------------------------------------


class TestMinPointsForScoring:
    @parameterized.expand(
        [
            (
                "diffs_1_lags_5_gives_7",
                {"preprocessing": {"diffs_n": 1, "lags_n": 5}},
                7,
            ),
            (
                "no_preprocessing_gives_absolute_minimum_2",
                {},
                2,
            ),
            (
                "diffs_only_gives_diffs_plus_1",
                {"preprocessing": {"diffs_n": 3}},
                4,
            ),
            (
                "lags_only_gives_lags_plus_1",
                {"preprocessing": {"lags_n": 10}},
                11,
            ),
            (
                "zero_diffs_and_zero_lags_gives_minimum_2",
                {"preprocessing": {"diffs_n": 0, "lags_n": 0}},
                2,
            ),
        ]
    )
    def test_single_detector_config(self, _name, sub_config: dict, expected: int):
        result = min_points_for_scoring(sub_config)
        assert result == expected, f"expected {expected}, got {result}"

    def test_ensemble_takes_max_across_sub_detectors(self):
        # Sub-detector A needs 7 points, B needs 3 points — ensemble should return 7
        config: dict[str, Any] = {
            "detectors": [
                {"preprocessing": {"diffs_n": 1, "lags_n": 5}},  # 1+5+1 = 7
                {"preprocessing": {"diffs_n": 1, "lags_n": 1}},  # 1+1+1 = 3
            ]
        }
        assert min_points_for_scoring(config) == 7

    def test_ensemble_with_no_preprocessing_on_any_detector_returns_minimum(self):
        config: dict[str, Any] = {
            "detectors": [
                {},
                {},
            ]
        }
        assert min_points_for_scoring(config) == 2

    def test_default_anomaly_detector_config_returns_7(self):
        from posthog.temporal.anomalies.common import DEFAULT_ANOMALY_DETECTOR_CONFIG

        # Default config has diffs_n=1, lags_n=5 on each sub-detector
        assert min_points_for_scoring(DEFAULT_ANOMALY_DETECTOR_CONFIG) == 7

    def test_single_detector_without_detectors_key_treated_as_its_own_sub_detector(self):
        config: dict[str, Any] = {"preprocessing": {"diffs_n": 2, "lags_n": 3}}
        # 2+3+1 = 6
        assert min_points_for_scoring(config) == 6


# ---------------------------------------------------------------------------
# interval_from_query
# ---------------------------------------------------------------------------


class TestIntervalFromQuery:
    @parameterized.expand(
        [
            ("hour_maps_to_hour", IntervalType.HOUR, "hour"),
            ("week_maps_to_week", IntervalType.WEEK, "week"),
            ("month_maps_to_month", IntervalType.MONTH, "month"),
            ("day_maps_to_day", IntervalType.DAY, "day"),
            ("second_falls_through_to_day", IntervalType.SECOND, "day"),
            ("minute_falls_through_to_day", IntervalType.MINUTE, "day"),
        ]
    )
    def test_interval_from_query(self, _name, interval: IntervalType, expected: str):
        query = _trends_query(interval=interval)
        result = interval_from_query(query)
        assert result == expected, f"IntervalType.{interval} should map to '{expected}', got '{result}'"


# ---------------------------------------------------------------------------
# is_time_series_trends_insight
# ---------------------------------------------------------------------------


class TestIsTimeSeriesTrendsInsight:
    def test_returns_true_and_query_for_trends_with_line_chart(self):
        query_dict = _trends_query(
            interval=IntervalType.DAY,
            display=ChartDisplayType.ACTIONS_LINE_GRAPH,
        ).model_dump()
        insight = _mock_insight(query_dict)

        with patch(
            "posthog.temporal.anomalies.common.upgrade_query",
            side_effect=_noop_upgrade_query,
        ):
            is_ts, trends_query = is_time_series_trends_insight(insight)

        assert is_ts is True
        assert trends_query is not None
        assert isinstance(trends_query, TrendsQuery)

    def test_returns_true_for_trends_with_no_display_set(self):
        query_dict = _trends_query(interval=IntervalType.WEEK).model_dump()
        insight = _mock_insight(query_dict)

        with patch(
            "posthog.temporal.anomalies.common.upgrade_query",
            side_effect=_noop_upgrade_query,
        ):
            is_ts, trends_query = is_time_series_trends_insight(insight)

        assert is_ts is True
        assert trends_query is not None

    @parameterized.expand(
        [
            ("bold_number", ChartDisplayType.BOLD_NUMBER),
            ("pie", ChartDisplayType.ACTIONS_PIE),
            ("bar_value", ChartDisplayType.ACTIONS_BAR_VALUE),
            ("table", ChartDisplayType.ACTIONS_TABLE),
            ("world_map", ChartDisplayType.WORLD_MAP),
        ]
    )
    def test_returns_false_for_non_time_series_display_types(self, _name, display: ChartDisplayType):
        query_dict = _trends_query(display=display).model_dump()
        insight = _mock_insight(query_dict)

        with patch(
            "posthog.temporal.anomalies.common.upgrade_query",
            side_effect=_noop_upgrade_query,
        ):
            is_ts, trends_query = is_time_series_trends_insight(insight)

        assert is_ts is False
        assert trends_query is None

    def test_returns_false_for_none_query(self):
        insight = _mock_insight(query=None)

        is_ts, trends_query = is_time_series_trends_insight(insight)

        assert is_ts is False
        assert trends_query is None

    def test_returns_false_for_non_trends_query_kind(self):
        query_dict = {"kind": "FunnelsQuery"}
        insight = _mock_insight(query_dict)

        with patch(
            "posthog.temporal.anomalies.common.upgrade_query",
            side_effect=_noop_upgrade_query,
        ):
            is_ts, trends_query = is_time_series_trends_insight(insight)

        assert is_ts is False
        assert trends_query is None

    def test_unwraps_insight_viz_node_wrapper(self):
        from posthog.schema import NodeKind

        inner_query = _trends_query(
            interval=IntervalType.DAY,
            display=ChartDisplayType.ACTIONS_LINE_GRAPH,
        ).model_dump()
        # Wrap in InsightVizNode
        wrapped = {"kind": NodeKind.INSIGHT_VIZ_NODE, "source": inner_query}
        insight = _mock_insight(wrapped)

        with patch(
            "posthog.temporal.anomalies.common.upgrade_query",
            side_effect=_noop_upgrade_query,
        ):
            is_ts, trends_query = is_time_series_trends_insight(insight)

        assert is_ts is True
        assert trends_query is not None

    def test_returns_false_for_invalid_trends_query_structure(self):
        # Provide a malformed dict that claims to be TrendsQuery but cannot be validated
        query_dict = {"kind": "TrendsQuery", "interval": "not_a_valid_interval_value_xyz"}
        insight = _mock_insight(query_dict)

        with patch(
            "posthog.temporal.anomalies.common.upgrade_query",
            side_effect=_noop_upgrade_query,
        ):
            is_ts, trends_query = is_time_series_trends_insight(insight)

        assert is_ts is False
        assert trends_query is None
