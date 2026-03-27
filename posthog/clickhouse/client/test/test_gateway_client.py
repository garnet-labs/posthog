import pytest
from unittest.mock import MagicMock, patch

from posthog.clickhouse.client.gateway_client import (
    GatewayClient,
    _clean_settings,
    _extract_query_tags,
    reset_gateway_client,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_gateway_client()
    yield
    reset_gateway_client()


@pytest.fixture
def mock_session():
    with patch("posthog.clickhouse.client.gateway_client.requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        yield session


def _make_client(mock_session: MagicMock) -> GatewayClient:
    client = GatewayClient(
        gateway_url="http://gateway:3100",
        service_token="test-token-123",
    )
    # Replace the session that was created in __init__ with our mock
    client.session = mock_session
    return client


class TestGatewayClientExecute:
    def test_sends_structured_json(self, mock_session: MagicMock):
        response = MagicMock()
        response.json.return_value = {"data": [["row1"], ["row2"]], "column_types": []}
        response.raise_for_status = MagicMock()
        mock_session.post.return_value = response

        client = _make_client(mock_session)
        result = client.execute(
            "SELECT * FROM events WHERE team_id = %(team_id)s",
            params={"team_id": 1},
            settings={"max_execution_time": 30, "log_comment": '{"team_id":1,"workload":"ONLINE"}'},
        )

        assert result == [["row1"], ["row2"]]

        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://gateway:3100/query"

        payload = call_args[1]["json"]
        assert payload["sql"] == "SELECT * FROM events WHERE team_id = %(team_id)s"
        assert payload["params"] == {"team_id": 1}
        # log_comment should be stripped from settings and moved to query_tags
        assert "log_comment" not in (payload["settings"] or {})
        assert payload["query_tags"] == {"team_id": 1, "workload": "ONLINE"}
        assert payload["settings"] == {"max_execution_time": 30}

    def test_includes_auth_header(self):
        client = GatewayClient(
            gateway_url="http://gateway:3100",
            service_token="my-secret-token",
        )
        assert client.session.headers["Authorization"] == "Bearer my-secret-token"
        assert client.session.headers["Content-Type"] == "application/json"

    def test_handles_with_column_types(self, mock_session: MagicMock):
        response = MagicMock()
        response.json.return_value = {
            "data": [["row1"]],
            "column_types": [["name", "String"]],
        }
        response.raise_for_status = MagicMock()
        mock_session.post.return_value = response

        client = _make_client(mock_session)
        result = client.execute("SELECT name FROM events", with_column_types=True)

        assert isinstance(result, tuple)
        assert len(result) == 2
        data, col_types = result
        assert data == [["row1"]]
        assert col_types == [["name", "String"]]

    def test_returns_written_rows_for_inserts(self, mock_session: MagicMock):
        response = MagicMock()
        response.json.return_value = {"data": [], "written_rows": 42}
        response.raise_for_status = MagicMock()
        mock_session.post.return_value = response

        client = _make_client(mock_session)
        result = client.execute("INSERT INTO events SELECT ...")

        assert result == 42

    def test_raises_on_http_error(self, mock_session: MagicMock):
        response = MagicMock()
        response.raise_for_status.side_effect = Exception("502 Bad Gateway")
        mock_session.post.return_value = response

        client = _make_client(mock_session)
        with pytest.raises(Exception, match="502 Bad Gateway"):
            client.execute("SELECT 1")

    def test_passes_query_id(self, mock_session: MagicMock):
        response = MagicMock()
        response.json.return_value = {"data": []}
        response.raise_for_status = MagicMock()
        mock_session.post.return_value = response

        client = _make_client(mock_session)
        client.execute("SELECT 1", query_id="abc-123")

        payload = mock_session.post.call_args[1]["json"]
        assert payload["query_id"] == "abc-123"

    def test_strips_trailing_slash_from_url(self):
        client = GatewayClient(gateway_url="http://gateway:3100/", service_token="tok")
        assert client.gateway_url == "http://gateway:3100"

    def test_context_manager_protocol(self, mock_session: MagicMock):
        client = _make_client(mock_session)
        with client as c:
            assert c is client

    def test_none_settings_passthrough(self, mock_session: MagicMock):
        response = MagicMock()
        response.json.return_value = {"data": []}
        response.raise_for_status = MagicMock()
        mock_session.post.return_value = response

        client = _make_client(mock_session)
        client.execute("SELECT 1", settings=None)

        payload = mock_session.post.call_args[1]["json"]
        assert payload["settings"] is None
        assert payload["query_tags"] is None


class TestExtractQueryTags:
    def test_extracts_json_log_comment(self):
        settings = {"log_comment": '{"team_id": 5, "workload": "ONLINE"}', "max_threads": 8}
        tags = _extract_query_tags(settings)
        assert tags == {"team_id": 5, "workload": "ONLINE"}

    def test_returns_none_when_no_log_comment(self):
        assert _extract_query_tags({"max_threads": 8}) is None
        assert _extract_query_tags(None) is None
        assert _extract_query_tags({}) is None

    def test_handles_invalid_json(self):
        tags = _extract_query_tags({"log_comment": "not-json{{"})
        assert tags == {"raw": "not-json{{"}


class TestCleanSettings:
    def test_strips_log_comment(self):
        settings = {"log_comment": '{"team_id": 1}', "max_threads": 8}
        cleaned = _clean_settings(settings)
        assert cleaned == {"max_threads": 8}

    def test_passthrough_none(self):
        assert _clean_settings(None) is None

    def test_passthrough_empty(self):
        assert _clean_settings({}) == {}


class TestGatewayRouting:
    def test_gateway_enabled_routes_to_gateway(self, settings):
        settings.CLICKHOUSE_GATEWAY_ENABLED = True
        settings.CLICKHOUSE_GATEWAY_URL = "http://gateway:3100"
        settings.CLICKHOUSE_GATEWAY_SERVICE_TOKEN = "tok"

        from posthog.clickhouse.client.connection import get_client_from_pool

        ctx = get_client_from_pool()
        # Should be a context manager that yields a GatewayClient
        with ctx as client:
            assert isinstance(client, GatewayClient)

    def test_gateway_disabled_routes_to_http(self, settings):
        settings.CLICKHOUSE_GATEWAY_ENABLED = False
        settings.CLICKHOUSE_USE_HTTP = True

        from posthog.clickhouse.client.connection import get_client_from_pool

        # Mock get_http_client since there's no CH server in unit tests
        mock_proxy = MagicMock()
        with patch("posthog.clickhouse.client.connection.get_http_client", return_value=mock_proxy):
            ctx = get_client_from_pool()
            assert ctx is mock_proxy
            assert not isinstance(ctx, GatewayClient)

    def test_gateway_disabled_falls_through_to_pool(self, settings):
        settings.CLICKHOUSE_GATEWAY_ENABLED = False
        settings.CLICKHOUSE_USE_HTTP = False
        settings.CLICKHOUSE_USE_HTTP_PER_TEAM = set()

        from posthog.clickhouse.client.connection import get_client_from_pool

        # Mock get_pool since there's no CH server in unit tests
        mock_pool = MagicMock()
        with patch("posthog.clickhouse.client.connection.get_pool", return_value=mock_pool):
            result = get_client_from_pool()
            assert not isinstance(result, GatewayClient)
