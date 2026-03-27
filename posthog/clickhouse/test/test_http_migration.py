from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from unittest.mock import MagicMock, patch

from posthog.clickhouse.client.connection import ProxyClient, get_client_from_pool, get_http_client


@contextmanager
def _mock_http_client(client: MagicMock) -> Iterator[MagicMock]:
    yield client


class TestDefaultUsesHTTP:
    def test_default_uses_http(self):
        """With default settings (CLICKHOUSE_USE_HTTP=True), get_client_from_pool returns an HTTP ProxyClient."""
        mock_http_client = MagicMock()

        with patch(
            "posthog.clickhouse.client.connection.get_http_client",
            return_value=_mock_http_client(mock_http_client),
        ) as mock_get_http:
            with patch("posthog.clickhouse.client.connection.settings") as mock_settings:
                mock_settings.CLICKHOUSE_GATEWAY_ENABLED = False
                mock_settings.CLICKHOUSE_USE_HTTP = True
                mock_settings.CLICKHOUSE_USE_HTTP_PER_TEAM = set()
                get_client_from_pool()
                mock_get_http.assert_called_once()

    @pytest.mark.parametrize("team_id", [None, 1, 99])
    def test_default_uses_http_regardless_of_team(self, team_id):
        with patch(
            "posthog.clickhouse.client.connection.get_http_client",
            return_value=_mock_http_client(MagicMock()),
        ) as mock_get_http:
            with patch("posthog.clickhouse.client.connection.settings") as mock_settings:
                mock_settings.CLICKHOUSE_GATEWAY_ENABLED = False
                mock_settings.CLICKHOUSE_USE_HTTP = True
                mock_settings.CLICKHOUSE_USE_HTTP_PER_TEAM = set()
                get_client_from_pool(team_id=team_id)
                mock_get_http.assert_called_once()


class TestEnvVarCanForceTCP:
    def test_env_var_false_uses_tcp_pool(self):
        mock_pool = MagicMock()
        mock_pool.get_client.return_value = MagicMock()

        with patch("posthog.clickhouse.client.connection.settings") as mock_settings:
            mock_settings.CLICKHOUSE_GATEWAY_ENABLED = False
            mock_settings.CLICKHOUSE_USE_HTTP = False
            mock_settings.CLICKHOUSE_USE_HTTP_PER_TEAM = set()
            with patch("posthog.clickhouse.client.connection.get_pool", return_value=mock_pool) as mock_get_pool:
                get_client_from_pool()
                mock_get_pool.assert_called_once()
                mock_pool.get_client.assert_called_once()


class TestPerTeamOverride:
    def test_per_team_override_routes_to_http(self):
        with patch(
            "posthog.clickhouse.client.connection.get_http_client",
            return_value=_mock_http_client(MagicMock()),
        ) as mock_get_http:
            with patch("posthog.clickhouse.client.connection.settings") as mock_settings:
                mock_settings.CLICKHOUSE_GATEWAY_ENABLED = False
                mock_settings.CLICKHOUSE_USE_HTTP = False
                mock_settings.CLICKHOUSE_USE_HTTP_PER_TEAM = {42}
                get_client_from_pool(team_id=42)
                mock_get_http.assert_called_once()

    def test_per_team_override_does_not_affect_other_teams(self):
        mock_pool = MagicMock()
        mock_pool.get_client.return_value = MagicMock()

        with patch("posthog.clickhouse.client.connection.settings") as mock_settings:
            mock_settings.CLICKHOUSE_GATEWAY_ENABLED = False
            mock_settings.CLICKHOUSE_USE_HTTP = False
            mock_settings.CLICKHOUSE_USE_HTTP_PER_TEAM = {42}
            with patch("posthog.clickhouse.client.connection.get_pool", return_value=mock_pool):
                get_client_from_pool(team_id=99)
                mock_pool.get_client.assert_called_once()


class TestProxyClientExecute:
    def test_execute_forwards_to_clickhouse_connect(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = {"written_rows": "0"}
        mock_result.result_set = [("row1",), ("row2",)]
        mock_client.query.return_value = mock_result

        proxy = ProxyClient(mock_client)
        result = proxy.execute("SELECT 1", params={"key": "val"}, settings={"max_threads": 4})

        mock_client.query.assert_called_once_with(
            query="SELECT 1",
            parameters={"key": "val"},
            settings={"max_threads": 4},
            column_oriented=False,
        )
        assert result == [("row1",), ("row2",)]

    def test_execute_with_query_id(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = {"written_rows": "0"}
        mock_result.result_set = []
        mock_client.query.return_value = mock_result

        proxy = ProxyClient(mock_client)
        settings: dict[str, object] = {"max_threads": 4}
        proxy.execute("SELECT 1", query_id="test-id", settings=settings)

        assert settings["query_id"] == "test-id"

    def test_execute_insert_returns_written_rows(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = {"written_rows": "5"}
        mock_client.query.return_value = mock_result

        proxy = ProxyClient(mock_client)
        result = proxy.execute("INSERT INTO t VALUES", settings={})

        assert result == 5


class TestProxyClientReturnsCorrectFormat:
    def test_with_column_types(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = {"written_rows": "0"}
        mock_result.result_set = [("Alice", 30), ("Bob", 25)]

        mock_name_type = MagicMock()
        mock_name_type.name = "String"
        mock_age_type = MagicMock()
        mock_age_type.name = "UInt32"

        mock_result.column_names = ["name", "age"]
        mock_result.column_types = [mock_name_type, mock_age_type]
        mock_client.query.return_value = mock_result

        proxy = ProxyClient(mock_client)
        result_set, column_types = proxy.execute("SELECT name, age FROM t", with_column_types=True, settings={})

        assert result_set == [("Alice", 30), ("Bob", 25)]
        assert column_types == [("name", "String"), ("age", "UInt32")]

    def test_without_column_types(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = {"written_rows": "0"}
        mock_result.result_set = [(1,), (2,)]
        mock_client.query.return_value = mock_result

        proxy = ProxyClient(mock_client)
        result = proxy.execute("SELECT 1", settings={})

        assert result == [(1,), (2,)]

    def test_context_manager_protocol(self):
        mock_client = MagicMock()
        proxy = ProxyClient(mock_client)

        with proxy as p:
            assert p is proxy


class TestGetHttpClientContextManager:
    def test_get_http_client_yields_proxy_client(self):
        mock_cc_client = MagicMock()

        with patch("posthog.clickhouse.client.connection.get_client", return_value=mock_cc_client):
            with patch("posthog.clickhouse.client.connection.settings") as mock_settings:
                mock_settings.CLICKHOUSE_HOST = "localhost"
                mock_settings.CLICKHOUSE_DATABASE = "default"
                mock_settings.CLICKHOUSE_SECURE = False
                mock_settings.CLICKHOUSE_USER = "default"
                mock_settings.CLICKHOUSE_PASSWORD = ""
                mock_settings.TEST = True
                with get_http_client() as client:
                    assert isinstance(client, ProxyClient)
