from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from posthog.test.base import BaseTest
from unittest.mock import MagicMock, patch

from django.test import TestCase

from posthog.schema import ErrorTrackingQuery

from products.error_tracking.dags.cache_warming import (
    DEFAULT_ERROR_TRACKING_QUERY,
    get_queries_for_team,
    get_teams_enabled_for_error_tracking_cache_warming,
    schedule_error_tracking_cache_warming_task,
    warm_error_tracking_cache_for_team_task,
)


class TestGetTeamsEnabled(TestCase):
    @patch("products.error_tracking.dags.cache_warming.get_instance_setting")
    def test_returns_configured_teams(self, mock_get_setting):
        mock_get_setting.return_value = [1, 2, 3]
        result = get_teams_enabled_for_error_tracking_cache_warming()
        assert result == [1, 2, 3]
        mock_get_setting.assert_called_once_with("ERROR_TRACKING_WARMING_TEAMS_TO_WARM")

    @patch("products.error_tracking.dags.cache_warming.get_instance_setting")
    def test_returns_empty_list_by_default(self, mock_get_setting):
        mock_get_setting.return_value = []
        result = get_teams_enabled_for_error_tracking_cache_warming()
        assert result == []


class TestDefaultQueryShape(TestCase):
    def test_default_query_is_valid_error_tracking_query(self):
        ErrorTrackingQuery(**DEFAULT_ERROR_TRACKING_QUERY)

    def test_default_query_fields(self):
        assert DEFAULT_ERROR_TRACKING_QUERY["kind"] == "ErrorTrackingQuery"
        assert DEFAULT_ERROR_TRACKING_QUERY["orderBy"] == "last_seen"
        assert DEFAULT_ERROR_TRACKING_QUERY["orderDirection"] == "DESC"
        assert DEFAULT_ERROR_TRACKING_QUERY["status"] == "active"
        assert DEFAULT_ERROR_TRACKING_QUERY["dateRange"] == {"date_from": "-7d", "date_to": None}
        assert DEFAULT_ERROR_TRACKING_QUERY["limit"] == 50
        assert DEFAULT_ERROR_TRACKING_QUERY["volumeResolution"] == 20
        assert DEFAULT_ERROR_TRACKING_QUERY["withAggregations"] is True
        assert DEFAULT_ERROR_TRACKING_QUERY["withFirstEvent"] is False
        assert DEFAULT_ERROR_TRACKING_QUERY["withLastEvent"] is False
        assert DEFAULT_ERROR_TRACKING_QUERY["filterTestAccounts"] is False


class TestGetQueriesForTeam(BaseTest):
    def test_returns_single_query_without_test_account_filters(self):
        self.team.test_account_filters = []
        self.team.save()

        queries = get_queries_for_team(self.team)
        assert len(queries) == 1
        assert queries[0]["filterTestAccounts"] is False

    def test_returns_two_queries_with_test_account_filters(self):
        self.team.test_account_filters = [{"key": "email", "value": "@posthog.com", "operator": "not_icontains"}]
        self.team.save()

        queries = get_queries_for_team(self.team)
        assert len(queries) == 2
        assert queries[0]["filterTestAccounts"] is False
        assert queries[1]["filterTestAccounts"] is True


class TestScheduleErrorTrackingCacheWarming(BaseTest):
    @patch("products.error_tracking.dags.cache_warming.warm_error_tracking_cache_for_team_task")
    @patch("products.error_tracking.dags.cache_warming.get_teams_enabled_for_error_tracking_cache_warming")
    def test_fans_out_per_team(self, mock_get_teams, mock_warm_task):
        mock_get_teams.return_value = [1, 2, 3]
        schedule_error_tracking_cache_warming_task()
        assert mock_warm_task.delay.call_count == 3
        mock_warm_task.delay.assert_any_call(1)
        mock_warm_task.delay.assert_any_call(2)
        mock_warm_task.delay.assert_any_call(3)

    @patch("products.error_tracking.dags.cache_warming.warm_error_tracking_cache_for_team_task")
    @patch("products.error_tracking.dags.cache_warming.get_teams_enabled_for_error_tracking_cache_warming")
    def test_no_teams_no_fanout(self, mock_get_teams, mock_warm_task):
        mock_get_teams.return_value = []
        schedule_error_tracking_cache_warming_task()
        mock_warm_task.delay.assert_not_called()


class TestWarmErrorTrackingCacheForTeamTask(BaseTest):
    @patch("products.error_tracking.dags.cache_warming.get_query_runner")
    @patch("products.error_tracking.dags.cache_warming.DjangoCacheQueryCacheManager")
    def test_skips_cached_queries(self, mock_cache_cls, mock_get_runner):
        mock_runner = MagicMock()
        mock_get_runner.return_value = mock_runner
        mock_runner.get_cache_key.return_value = "test_key"

        mock_cache = MagicMock()
        mock_cache_cls.return_value = mock_cache
        mock_cache.get_cache_data.return_value = {
            "last_refresh": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
        }
        mock_runner._is_stale.return_value = False

        warm_error_tracking_cache_for_team_task(self.team.pk)

        mock_runner.run.assert_not_called()

    @patch("products.error_tracking.dags.cache_warming.tag_queries")
    @patch("products.error_tracking.dags.cache_warming.get_query_runner")
    @patch("products.error_tracking.dags.cache_warming.DjangoCacheQueryCacheManager")
    def test_warms_stale_queries(self, mock_cache_cls, mock_get_runner, mock_tag):
        mock_runner = MagicMock()
        mock_get_runner.return_value = mock_runner
        mock_runner.get_cache_key.return_value = "test_key"

        mock_cache = MagicMock()
        mock_cache_cls.return_value = mock_cache
        mock_cache.get_cache_data.return_value = {
            "last_refresh": (datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=2)).isoformat(),
        }
        mock_runner._is_stale.return_value = True

        warm_error_tracking_cache_for_team_task(self.team.pk)

        mock_runner.run.assert_called_once()

    @patch("products.error_tracking.dags.cache_warming.tag_queries")
    @patch("products.error_tracking.dags.cache_warming.get_query_runner")
    @patch("products.error_tracking.dags.cache_warming.DjangoCacheQueryCacheManager")
    def test_warms_uncached_queries(self, mock_cache_cls, mock_get_runner, mock_tag):
        mock_runner = MagicMock()
        mock_get_runner.return_value = mock_runner
        mock_runner.get_cache_key.return_value = "test_key"

        mock_cache = MagicMock()
        mock_cache_cls.return_value = mock_cache
        mock_cache.get_cache_data.return_value = None

        warm_error_tracking_cache_for_team_task(self.team.pk)

        mock_runner.run.assert_called_once()

    @patch("products.error_tracking.dags.cache_warming.get_query_runner")
    def test_handles_missing_team(self, mock_get_runner):
        warm_error_tracking_cache_for_team_task(999999)

        mock_get_runner.assert_not_called()
