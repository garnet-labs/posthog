import json
from datetime import datetime

from unittest.mock import MagicMock, patch

from django.test import TestCase

from posthog.models.health_issue import HealthIssue

from products.growth.backend.constants import TEAM_SDK_VERSIONS_CACHE_EXPIRY, team_sdk_versions_key
from products.growth.backend.temporal.health_checks.sdk_outdated import SdkOutdatedCheck, _group_by_team


def _make_github_data(latest_version: str, release_dates: dict | None = None) -> dict:
    return {
        "latestVersion": latest_version,
        "releaseDates": release_dates or {},
    }


def _make_ch_rows(team_id: int, entries: list[tuple[str, str, str, int]]) -> list[tuple]:
    """Build ClickHouse result rows: (team_id, lib, lib_version, max_timestamp, event_count)."""
    return [(team_id, lib, ver, datetime.fromisoformat(ts), count) for lib, ver, ts, count in entries]


class TestSdkOutdatedCheck(TestCase):
    def setUp(self):
        self.check = SdkOutdatedCheck()

    @patch("products.growth.backend.temporal.health_checks.sdk_outdated.execute_clickhouse_health_team_query")
    @patch("products.growth.backend.temporal.health_checks.sdk_outdated.get_client")
    def test_detects_outdated_sdk_with_enriched_payload(self, mock_get_client: MagicMock, mock_ch_query: MagicMock):
        mock_redis = MagicMock()
        mock_get_client.return_value = mock_redis

        github_data = {"web": _make_github_data("1.200.0", {"1.198.0": "2026-03-01T00:00:00Z"})}
        mock_redis.mget.return_value = [json.dumps(github_data["web"]).encode()]
        mock_redis.pipeline.return_value = mock_redis

        mock_ch_query.return_value = _make_ch_rows(
            1,
            [
                ("web", "1.198.0", "2026-03-20T12:00:00", 5000),
                ("web", "1.195.0", "2026-03-18T08:00:00", 1000),
            ],
        )

        results = self.check.detect([1])

        assert 1 in results
        assert len(results[1]) == 1

        issue = results[1][0]
        assert issue.severity == HealthIssue.Severity.WARNING
        assert issue.payload["sdk_name"] == "web"
        assert issue.payload["latest_version"] == "1.200.0"
        assert len(issue.payload["usage"]) == 2
        assert issue.payload["usage"][0]["lib_version"] == "1.198.0"
        assert issue.payload["usage"][0]["count"] == 5000
        assert issue.payload["usage"][0]["is_latest"] is False
        assert issue.payload["usage"][0]["release_date"] == "2026-03-01T00:00:00Z"
        assert issue.payload["usage"][1]["lib_version"] == "1.195.0"
        assert issue.payload["usage"][1]["release_date"] is None
        assert issue.hash_keys == ["sdk_name"]

    @patch("products.growth.backend.temporal.health_checks.sdk_outdated.execute_clickhouse_health_team_query")
    @patch("products.growth.backend.temporal.health_checks.sdk_outdated.get_client")
    def test_skips_team_on_latest_version(self, mock_get_client: MagicMock, mock_ch_query: MagicMock):
        mock_redis = MagicMock()
        mock_get_client.return_value = mock_redis

        mock_redis.mget.return_value = [json.dumps(_make_github_data("1.200.0")).encode()]
        mock_redis.pipeline.return_value = mock_redis

        mock_ch_query.return_value = _make_ch_rows(1, [("web", "1.200.0", "2026-03-20T12:00:00", 5000)])

        results = self.check.detect([1])

        assert results == {}

    @patch("products.growth.backend.temporal.health_checks.sdk_outdated.execute_clickhouse_health_team_query")
    @patch("products.growth.backend.temporal.health_checks.sdk_outdated.get_client")
    def test_returns_empty_when_no_github_data(self, mock_get_client: MagicMock, mock_ch_query: MagicMock):
        mock_redis = MagicMock()
        mock_get_client.return_value = mock_redis
        mock_redis.mget.return_value = [None]

        results = self.check.detect([1])

        assert results == {}
        mock_ch_query.assert_not_called()

    @patch("products.growth.backend.temporal.health_checks.sdk_outdated.execute_clickhouse_health_team_query")
    @patch("products.growth.backend.temporal.health_checks.sdk_outdated.get_client")
    def test_caches_results_in_redis(self, mock_get_client: MagicMock, mock_ch_query: MagicMock):
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_get_client.return_value = mock_redis
        mock_redis.pipeline.return_value = mock_pipe

        mock_redis.mget.return_value = [json.dumps(_make_github_data("1.200.0")).encode()]

        mock_ch_query.return_value = _make_ch_rows(1, [("web", "1.198.0", "2026-03-20T12:00:00", 5000)])

        self.check.detect([1, 2])

        # Team 1 has data, team 2 has none — both should be cached
        assert mock_pipe.setex.call_count == 2
        mock_pipe.setex.assert_any_call(
            team_sdk_versions_key(1),
            TEAM_SDK_VERSIONS_CACHE_EXPIRY,
            json.dumps(
                {
                    "web": [
                        {
                            "lib_version": "1.198.0",
                            "max_timestamp": str(datetime.fromisoformat("2026-03-20T12:00:00")),
                            "count": 5000,
                        }
                    ]
                }
            ),
        )
        mock_pipe.setex.assert_any_call(
            team_sdk_versions_key(2),
            TEAM_SDK_VERSIONS_CACHE_EXPIRY,
            json.dumps({}),
        )
        mock_pipe.execute.assert_called_once()

    @patch("products.growth.backend.temporal.health_checks.sdk_outdated.execute_clickhouse_health_team_query")
    @patch("products.growth.backend.temporal.health_checks.sdk_outdated.get_client")
    def test_filters_to_known_sdk_types(self, mock_get_client: MagicMock, mock_ch_query: MagicMock):
        mock_redis = MagicMock()
        mock_get_client.return_value = mock_redis
        mock_redis.pipeline.return_value = mock_redis

        mock_redis.mget.return_value = [json.dumps(_make_github_data("1.0.0")).encode()]

        mock_ch_query.return_value = [
            (1, "web", "0.9.0", datetime(2026, 3, 20), 100),
            (1, "unknown-sdk", "1.0.0", datetime(2026, 3, 20), 50),
        ]

        results = self.check.detect([1])

        # Only "web" should produce an issue, "unknown-sdk" is filtered out
        assert 1 in results
        assert len(results[1]) == 1
        assert results[1][0].payload["sdk_name"] == "web"


class TestGroupByTeam(TestCase):
    def test_groups_rows_by_team_and_lib(self):
        rows = [
            (1, "web", "1.0.0", datetime(2026, 3, 20), 100),
            (1, "web", "0.9.0", datetime(2026, 3, 18), 50),
            (2, "posthog-python", "3.0.0", datetime(2026, 3, 19), 200),
        ]

        result = _group_by_team(rows)

        assert set(result.keys()) == {1, 2}
        assert len(result[1]["web"]) == 2
        assert result[1]["web"][0]["lib_version"] == "1.0.0"
        assert result[2]["posthog-python"][0]["lib_version"] == "3.0.0"

    def test_filters_unknown_sdk_types(self):
        rows = [
            (1, "unknown-lib", "1.0.0", datetime(2026, 3, 20), 100),
        ]

        result = _group_by_team(rows)

        assert result == {}
