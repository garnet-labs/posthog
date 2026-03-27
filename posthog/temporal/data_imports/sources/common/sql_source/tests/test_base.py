from __future__ import annotations

from contextlib import contextmanager

import pytest
from unittest.mock import MagicMock, patch

from posthog.schema import SourceConfig

from posthog.temporal.data_imports.sources.common.sql_source.base import SQLSource
from posthog.temporal.data_imports.sources.common.sql_source.exceptions import SSLRequiredError
from posthog.temporal.data_imports.sources.common.sql_source.typing import (
    ExceptionHandler,
    ForeignKeyMapping,
    RowCountMapping,
)
from posthog.temporal.data_imports.sources.generated_configs import PostgresSourceConfig

from products.data_warehouse.backend.types import ExternalDataSourceType, IncrementalFieldType

# -- Test fixtures --


# A minimal config for unit tests — reuse PostgresSourceConfig as a convenient concrete config
def _make_config(**kwargs) -> PostgresSourceConfig:
    defaults: dict = {
        "host": "localhost",
        "port": 5432,
        "user": "test",
        "password": "test",
        "database": "testdb",
        "schema": "public",
        "ssh_tunnel": None,
        "connection_string": None,
    }
    defaults.update(kwargs)
    return PostgresSourceConfig(**defaults)  # type: ignore[arg-type]


def _no_incremental_filter(columns):
    return []


def _fake_source_creator(**kwargs):
    return MagicMock()


class _FakeSQLSource(SQLSource[PostgresSourceConfig]):
    """Minimal concrete SQLSource for testing the base class orchestration."""

    source_display_name = "FakeDB"
    _schema_fetcher = staticmethod(lambda **kw: {"users": [("id", "integer", False), ("name", "text", True)]})
    _incremental_filter = staticmethod(
        lambda cols: [
            (name, IncrementalFieldType.Integer, nullable) for name, typ, nullable in cols if typ == "integer"
        ]
    )
    _source_creator = staticmethod(_fake_source_creator)

    @property
    def source_type(self) -> ExternalDataSourceType:
        return ExternalDataSourceType.POSTGRES

    @property
    def get_source_config(self) -> SourceConfig:
        return MagicMock()


@contextmanager
def _ssh_tunnel_noop(config):
    """Context manager that returns (host, port) from the config without SSH."""
    yield config.host, config.port


class TestGetSchemas:
    @pytest.fixture
    def source(self):
        return _FakeSQLSource()

    def test_basic_schema_list(self, source):
        config = _make_config()
        with patch.object(source, "with_ssh_tunnel", side_effect=_ssh_tunnel_noop):
            schemas = source.get_schemas(config, team_id=1)

        assert len(schemas) == 1
        schema = schemas[0]
        assert schema.name == "users"
        assert schema.supports_incremental is True
        assert schema.supports_append is True
        assert len(schema.incremental_fields) == 1
        assert schema.incremental_fields[0]["field"] == "id"

    def test_columns_always_populated(self, source):
        config = _make_config()
        with patch.object(source, "with_ssh_tunnel", side_effect=_ssh_tunnel_noop):
            schemas = source.get_schemas(config, team_id=1)

        assert schemas[0].columns == [("id", "integer", False), ("name", "text", True)]

    def test_foreign_keys_hook_enriches_schemas(self, source):
        config = _make_config()
        fk_data: ForeignKeyMapping = {"users": [("org_id", "organisations", "id")]}

        with patch.object(source, "with_ssh_tunnel", side_effect=_ssh_tunnel_noop):
            with patch.object(source, "_get_foreign_keys", return_value=fk_data):
                schemas = source.get_schemas(config, team_id=1)

        assert schemas[0].foreign_keys == [("org_id", "organisations", "id")]

    def test_foreign_keys_default_empty(self, source):
        config = _make_config()
        with patch.object(source, "with_ssh_tunnel", side_effect=_ssh_tunnel_noop):
            schemas = source.get_schemas(config, team_id=1)

        assert schemas[0].foreign_keys == []

    def test_row_counts_hook_only_called_when_requested(self, source):
        config = _make_config()
        with patch.object(source, "with_ssh_tunnel", side_effect=_ssh_tunnel_noop):
            with patch.object(source, "_get_row_counts", return_value={"users": 42}) as mock_counts:
                source.get_schemas(config, team_id=1, with_counts=False)
                mock_counts.assert_not_called()

                source.get_schemas(config, team_id=1, with_counts=True)
                mock_counts.assert_called_once()

    def test_row_counts_enriches_schemas(self, source):
        config = _make_config()
        counts: RowCountMapping = {"users": 999}
        with patch.object(source, "with_ssh_tunnel", side_effect=_ssh_tunnel_noop):
            with patch.object(source, "_get_row_counts", return_value=counts):
                schemas = source.get_schemas(config, team_id=1, with_counts=True)

        assert schemas[0].row_count == 999

    def test_row_count_none_when_not_requested(self, source):
        config = _make_config()
        with patch.object(source, "with_ssh_tunnel", side_effect=_ssh_tunnel_noop):
            schemas = source.get_schemas(config, team_id=1, with_counts=False)

        assert schemas[0].row_count is None

    def test_names_filter_passed_to_schema_fetcher(self, source):
        config = _make_config()
        with patch.object(source, "with_ssh_tunnel", side_effect=_ssh_tunnel_noop):
            with patch.object(
                type(source),
                "_schema_fetcher",
                staticmethod(lambda **kw: {"orders": []} if kw.get("names") == ["orders"] else {}),
            ):
                schemas = source.get_schemas(config, team_id=1, names=["orders"])

        assert len(schemas) == 1
        assert schemas[0].name == "orders"


class TestValidateCredentials:
    @pytest.fixture
    def source(self):
        return _FakeSQLSource()

    def test_success(self, source):
        config = _make_config()
        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(True, None)):
                with patch.object(source, "get_schemas", return_value=[]):
                    ok, err = source.validate_credentials(config, team_id=1)

        assert ok is True
        assert err is None

    def test_ssh_failure_short_circuits(self, source):
        config = _make_config()
        with patch.object(source, "ssh_tunnel_is_valid", return_value=(False, "SSH key invalid")):
            ok, err = source.validate_credentials(config, team_id=1)

        assert ok is False
        assert err == "SSH key invalid"

    def test_host_invalid_short_circuits(self, source):
        config = _make_config()
        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(False, "Blocked host")):
                ok, err = source.validate_credentials(config, team_id=1)

        assert ok is False
        assert err == "Blocked host"

    def test_extra_handler_fires_before_generic(self, source):
        class MyError(Exception):
            pass

        handler: ExceptionHandler = lambda e: (False, "my specific message")

        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(True, None)):
                with patch.object(source, "get_schemas", side_effect=MyError("boom")):
                    with patch.object(source, "_get_extra_exception_handlers", return_value=[(MyError, handler)]):
                        ok, err = source.validate_credentials(config=_make_config(), team_id=1)

        assert ok is False
        assert err == "my specific message"

    def test_extra_handler_only_fires_on_matching_type(self, source):
        class MyError(Exception):
            pass

        class OtherError(Exception):
            pass

        handler: ExceptionHandler = lambda e: (False, "should not appear")

        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(True, None)):
                with patch.object(source, "get_schemas", side_effect=OtherError("other")):
                    with patch.object(source, "_get_extra_exception_handlers", return_value=[(MyError, handler)]):
                        with patch("posthog.temporal.data_imports.sources.common.sql_source.base.capture_exception"):
                            ok, err = source.validate_credentials(config=_make_config(), team_id=1)

        assert ok is False
        assert "FakeDB" in err  # generic message, not the handler's message

    def test_connection_error_class_and_map_used(self, source):
        class DBError(Exception):
            pass

        error_map = {"bad password": "Invalid credentials"}

        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(True, None)):
                with patch.object(source, "get_schemas", side_effect=DBError("bad password for user")):
                    with patch.object(source, "_get_connection_error_class", return_value=DBError):
                        with patch.object(source, "_get_connection_error_map", return_value=error_map):
                            ok, err = source.validate_credentials(config=_make_config(), team_id=1)

        assert ok is False
        assert err == "Invalid credentials"

    def test_generic_exception_returns_display_name_message(self, source):
        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(True, None)):
                with patch.object(source, "get_schemas", side_effect=RuntimeError("unexpected")):
                    with patch("posthog.temporal.data_imports.sources.common.sql_source.base.capture_exception"):
                        ok, err = source.validate_credentials(config=_make_config(), team_id=1)

        assert ok is False
        assert "FakeDB" in err

    def test_ssh_tunnel_error_returns_value_message(self, source):
        from sshtunnel import BaseSSHTunnelForwarderError

        tunnel_error = BaseSSHTunnelForwarderError("tunnel down")

        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(True, None)):
                with patch.object(source, "get_schemas", side_effect=tunnel_error):
                    ok, err = source.validate_credentials(config=_make_config(), team_id=1)

        assert ok is False
        # e.value is used when truthy; this error has "tunnel down" as its value
        assert err == "tunnel down"

    def test_ssh_tunnel_error_fallback_message_when_no_value(self, source):
        from sshtunnel import BaseSSHTunnelForwarderError

        tunnel_error = BaseSSHTunnelForwarderError()  # no message → e.value is None/empty

        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(True, None)):
                with patch.object(source, "get_schemas", side_effect=tunnel_error):
                    ok, err = source.validate_credentials(config=_make_config(), team_id=1)

        assert ok is False
        assert "SSH tunnel" in err

    def test_ssl_required_error_via_extra_handler(self, source):
        """SSLRequiredError is a typical use case for _get_extra_exception_handlers."""
        ssl_err = SSLRequiredError("SSL/TLS is required but not supported")

        def ssl_handler(e: Exception) -> tuple[bool, str | None]:
            return False, str(e)

        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(True, None)):
                with patch.object(source, "get_schemas", side_effect=ssl_err):
                    with patch.object(
                        source, "_get_extra_exception_handlers", return_value=[(SSLRequiredError, ssl_handler)]
                    ):
                        ok, err = source.validate_credentials(config=_make_config(), team_id=1)

        assert ok is False
        assert "SSL/TLS" in err
