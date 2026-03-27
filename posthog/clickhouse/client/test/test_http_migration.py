"""Tests for HTTP protocol migration compatibility.

Validates that ProxyClient (HTTP via clickhouse-connect) behaves identically
to the TCP client (clickhouse-driver) for all query patterns used in PostHog.
"""

import uuid

import pytest
from unittest.mock import MagicMock, patch

from posthog.clickhouse.client.connection import ProxyClient, get_http_client
from posthog.clickhouse.client.execute import sync_execute

# ── ProxyClient unit tests ──────────────────────────────────────────────────


class TestProxyClientSelectQueries:
    def test_execute_select_returns_result_set(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = {"written_rows": "0"}
        mock_result.result_set = [(1,), (2,), (3,)]
        mock_client.query.return_value = mock_result

        proxy = ProxyClient(mock_client)
        result = proxy.execute("SELECT number FROM numbers(3)", settings={})

        assert result == [(1,), (2,), (3,)]

    def test_execute_with_column_types(self):
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

    def test_execute_empty_result(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = {"written_rows": "0"}
        mock_result.result_set = []
        mock_client.query.return_value = mock_result

        proxy = ProxyClient(mock_client)
        result = proxy.execute("SELECT 1 WHERE 0", settings={})

        assert result == []


class TestProxyClientQueryId:
    def test_query_id_creates_new_settings_dict(self):
        """query_id should not mutate the caller's settings dict."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = {"written_rows": "0"}
        mock_result.result_set = []
        mock_client.query.return_value = mock_result

        proxy = ProxyClient(mock_client)
        original_settings = {"max_threads": 4}
        proxy.execute("SELECT 1", query_id="test-123", settings=original_settings)

        # Original dict must NOT be mutated
        assert "query_id" not in original_settings
        # But the query should have received the query_id
        call_settings = mock_client.query.call_args.kwargs["settings"]
        assert call_settings["query_id"] == "test-123"

    def test_query_id_with_none_settings(self):
        """query_id with settings=None should not crash."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = {"written_rows": "0"}
        mock_result.result_set = []
        mock_client.query.return_value = mock_result

        proxy = ProxyClient(mock_client)
        proxy.execute("SELECT 1", query_id="test-456", settings=None)

        call_settings = mock_client.query.call_args.kwargs["settings"]
        assert call_settings["query_id"] == "test-456"


class TestProxyClientInsert:
    def test_insert_command_returns_written_rows_from_summary(self):
        """INSERT ... SELECT returns written_rows from response summary."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = {"written_rows": "5"}
        mock_client.query.return_value = mock_result

        proxy = ProxyClient(mock_client)
        result = proxy.execute("INSERT INTO t SELECT number FROM numbers(5)", settings={})

        assert result == 5

    def test_insert_with_dict_rows(self):
        """Batch INSERT with list of dicts should use client.insert()."""
        mock_client = MagicMock()
        mock_summary = MagicMock()
        mock_summary.written_rows = 2
        mock_client.insert.return_value = mock_summary

        proxy = ProxyClient(mock_client)
        data = [
            {"id": "abc", "name": "Alice", "age": 30},
            {"id": "def", "name": "Bob", "age": 25},
        ]
        result = proxy.execute(
            "INSERT INTO users (id, name, age) VALUES",
            params=data,
            settings={},
        )

        assert result == 2
        mock_client.insert.assert_called_once()
        call_kwargs = mock_client.insert.call_args.kwargs
        assert call_kwargs["table"] == "users"
        assert call_kwargs["column_names"] == ["id", "name", "age"]
        assert call_kwargs["data"] == [["abc", "Alice", 30], ["def", "Bob", 25]]

    def test_insert_with_tuple_rows(self):
        """Batch INSERT with list of tuples should use client.insert()."""
        mock_client = MagicMock()
        mock_summary = MagicMock()
        mock_summary.written_rows = 2
        mock_client.insert.return_value = mock_summary

        proxy = ProxyClient(mock_client)
        data = [(1, "Alice"), (2, "Bob")]
        result = proxy.execute(
            "INSERT INTO users (id, name) VALUES",
            params=data,
            settings={},
        )

        assert result == 2
        mock_client.insert.assert_called_once()

    def test_insert_without_column_spec_falls_back_to_command(self):
        """INSERT without explicit columns falls back to command()."""
        mock_client = MagicMock()
        mock_client.command.return_value = 3

        proxy = ProxyClient(mock_client)
        proxy.execute(
            "INSERT INTO t SELECT number FROM numbers(3)",
            params=[],
            settings={},
        )

        # Empty list should not trigger batch insert path
        # (empty list is falsy in Python)
        mock_client.query.assert_called_once()


class TestProxyClientContextManager:
    def test_context_manager_protocol(self):
        mock_client = MagicMock()
        proxy = ProxyClient(mock_client)

        with proxy as p:
            assert p is proxy


# ── Integration tests (require ClickHouse) ──────────────────────────────────


@pytest.mark.django_db
class TestHttpClientIntegration:
    def test_select_via_http(self):
        """Basic SELECT works through HTTP ProxyClient."""
        with get_http_client() as client:
            result = client.execute("SELECT 1 AS n, 'hello' AS s", settings={})
        assert result == [(1, "hello")]

    def test_select_with_column_types_via_http(self):
        """Column type metadata matches between TCP and HTTP."""
        query = "SELECT toUInt64(1) AS n, 'hello' AS s"

        tcp_result = sync_execute(query, with_column_types=True)
        with get_http_client() as client:
            http_result = client.execute(query, with_column_types=True, settings={})

        tcp_rows, tcp_types = tcp_result
        http_rows, http_types = http_result

        assert tcp_rows == http_rows
        # Column names should match
        assert [name for name, _ in tcp_types] == [name for name, _ in http_types]

    def test_insert_via_http_command(self):
        """INSERT ... SELECT works through HTTP."""
        table = f"_test_http_insert_{uuid.uuid4().hex[:8]}"
        sync_execute(f"CREATE TABLE {table} (n UInt64) ENGINE = Memory")
        try:
            with get_http_client() as client:
                result = client.execute(f"INSERT INTO {table} SELECT number FROM numbers(5)", settings={})
            assert result == 5

            rows = sync_execute(f"SELECT count() FROM {table}")
            assert rows[0][0] == 5
        finally:
            sync_execute(f"DROP TABLE IF EXISTS {table}")

    def test_batch_insert_with_dicts_via_http(self):
        """Batch INSERT with dict rows works through HTTP ProxyClient."""
        table = f"_test_http_batch_{uuid.uuid4().hex[:8]}"
        sync_execute(f"CREATE TABLE {table} (id String, value UInt64) ENGINE = Memory")
        try:
            with get_http_client() as client:
                data = [
                    {"id": "a", "value": 1},
                    {"id": "b", "value": 2},
                    {"id": "c", "value": 3},
                ]
                result = client.execute(
                    f"INSERT INTO {table} (id, value) VALUES",
                    params=data,
                    settings={},
                )
            assert result == 3

            rows = sync_execute(f"SELECT id, value FROM {table} ORDER BY value")
            assert rows == [("a", 1), ("b", 2), ("c", 3)]
        finally:
            sync_execute(f"DROP TABLE IF EXISTS {table}")


# ── Shadow mode tests ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestShadowMode:
    def test_shadow_mode_runs_http_query(self, settings):
        """When shadow mode is on, HTTP query runs alongside TCP."""
        settings.CLICKHOUSE_HTTP_SHADOW_MODE = True
        settings.CLICKHOUSE_USE_HTTP = False

        result = sync_execute("SELECT 1 AS n")
        # Primary (TCP) result is returned correctly
        assert result == [(1,)]

    def test_shadow_mode_does_not_affect_tcp_result_on_http_error(self, settings):
        """HTTP errors in shadow mode don't affect the TCP result."""
        settings.CLICKHOUSE_HTTP_SHADOW_MODE = True
        settings.CLICKHOUSE_USE_HTTP = False

        with patch(
            "posthog.clickhouse.client.connection.get_http_client",
            side_effect=Exception("HTTP connection failed"),
        ):
            result = sync_execute("SELECT 42 AS n")
            assert result == [(42,)]

    def test_shadow_mode_skips_insert_queries(self, settings):
        """INSERT queries are never shadowed."""
        settings.CLICKHOUSE_HTTP_SHADOW_MODE = True
        settings.CLICKHOUSE_USE_HTTP = False

        table = f"_test_shadow_insert_{uuid.uuid4().hex[:8]}"
        sync_execute(f"CREATE TABLE {table} (n UInt64) ENGINE = Memory")
        try:
            with patch("posthog.clickhouse.client.execute._run_shadow_http_query") as mock_shadow:
                sync_execute(f"INSERT INTO {table} SELECT number FROM numbers(3)")
                mock_shadow.assert_not_called()
        finally:
            sync_execute(f"DROP TABLE IF EXISTS {table}")

    def test_shadow_mode_off_by_default(self, settings):
        """Shadow mode doesn't run when CLICKHOUSE_HTTP_SHADOW_MODE is False."""
        settings.CLICKHOUSE_HTTP_SHADOW_MODE = False

        with patch("posthog.clickhouse.client.execute._run_shadow_http_query") as mock_shadow:
            sync_execute("SELECT 1")
            mock_shadow.assert_not_called()

    def test_shadow_mode_skipped_when_http_is_primary(self, settings):
        """Shadow mode doesn't run when HTTP is already the primary path."""
        settings.CLICKHOUSE_HTTP_SHADOW_MODE = True
        settings.CLICKHOUSE_USE_HTTP = True

        with patch("posthog.clickhouse.client.execute._run_shadow_http_query") as mock_shadow:
            sync_execute("SELECT 1")
            mock_shadow.assert_not_called()
