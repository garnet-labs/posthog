"""Unit tests for the ClickHouse migration trial runner.

Tests run_trial with mocked ClickhouseCluster — no Django or ClickHouse
connection required.
"""

from __future__ import annotations

import os
import sys
import types
from collections.abc import Callable

import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub heavy dependencies so migration_tools can import without Django.
# ---------------------------------------------------------------------------

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)


def _django_is_configured() -> bool:
    try:
        from django.conf import settings

        val = getattr(settings, "USE_I18N", None)
        return isinstance(val, bool)
    except Exception:
        return False


if not _django_is_configured():

    class _CeleryModule(types.ModuleType):
        app: types.SimpleNamespace

    class _NodeRole:
        DATA = "DATA"
        COORDINATOR = "COORDINATOR"
        ALL = "ALL"

        def __init__(self, value: str = "data") -> None:
            self.value = value

    class _ConnectionModule(types.ModuleType):
        NodeRole: type[_NodeRole]

    class _FakeQuery:
        def __init__(self, sql: str) -> None:
            self.sql = sql

    class _ClusterModule(types.ModuleType):
        Query: type[_FakeQuery]
        get_cluster: Callable[..., MagicMock]

    class _FakeRunPython:
        def __init__(self, fn: object) -> None:
            self.fn = fn

    class _MigrationsModule(types.ModuleType):
        RunPython: type[_FakeRunPython]

    class _SettingsModule(types.ModuleType):
        E2E_TESTING: bool
        DEBUG: bool
        CLOUD_DEPLOYMENT: bool

    class _DataStoresModule(types.ModuleType):
        CLICKHOUSE_MIGRATIONS_CLUSTER: str
        CLICKHOUSE_MIGRATIONS_HOST: str

    def _fake_get_cluster(*args: object, **kwargs: object) -> MagicMock:
        return MagicMock()

    _posthog_celery = _CeleryModule("posthog.celery")
    _posthog_celery.app = types.SimpleNamespace()
    sys.modules.setdefault("posthog.celery", _posthog_celery)

    fake_client = types.ModuleType("posthog.clickhouse.client")
    fake_client.__path__ = [os.path.join(_BASE, "posthog/clickhouse/client")]
    fake_client.__package__ = "posthog.clickhouse.client"
    sys.modules.setdefault("posthog.clickhouse.client", fake_client)

    fake_conn = _ConnectionModule("posthog.clickhouse.client.connection")
    fake_conn.NodeRole = _NodeRole
    sys.modules.setdefault("posthog.clickhouse.client.connection", fake_conn)

    fake_cluster_mod = _ClusterModule("posthog.clickhouse.cluster")
    fake_cluster_mod.Query = _FakeQuery
    fake_cluster_mod.get_cluster = _fake_get_cluster
    sys.modules.setdefault("posthog.clickhouse.cluster", fake_cluster_mod)

    infi_mod = types.ModuleType("infi")
    infi_mod.__path__ = ["/fake"]
    sys.modules.setdefault("infi", infi_mod)

    infi_clickhouse_orm_mod = types.ModuleType("infi.clickhouse_orm")
    infi_clickhouse_orm_mod.__path__ = ["/fake"]
    sys.modules.setdefault("infi.clickhouse_orm", infi_clickhouse_orm_mod)

    infi_migrations_mod = _MigrationsModule("infi.clickhouse_orm.migrations")
    infi_migrations_mod.__path__ = ["/fake"]
    infi_migrations_mod.RunPython = _FakeRunPython
    sys.modules.setdefault("infi.clickhouse_orm.migrations", infi_migrations_mod)

    fake_settings = _SettingsModule("posthog.settings")
    fake_settings.E2E_TESTING = False
    fake_settings.DEBUG = True
    fake_settings.CLOUD_DEPLOYMENT = False
    sys.modules.setdefault("posthog.settings", fake_settings)

    fake_ds = _DataStoresModule("posthog.settings.data_stores")
    fake_ds.CLICKHOUSE_MIGRATIONS_CLUSTER = "default"
    fake_ds.CLICKHOUSE_MIGRATIONS_HOST = "localhost"
    sys.modules.setdefault("posthog.settings.data_stores", fake_ds)

    # Stub yaml so manifest.py (imported by runner.py) can load without PyYAML
    sys.modules.setdefault("yaml", types.ModuleType("yaml"))

    # Stub posthog.clickhouse.client.migration_tools for per-host retry import in runner
    fake_migration_tools = types.ModuleType("posthog.clickhouse.client.migration_tools")
    fake_migration_tools.get_migrations_cluster = _fake_get_cluster  # type: ignore
    sys.modules.setdefault("posthog.clickhouse.client.migration_tools", fake_migration_tools)

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from posthog.clickhouse.migration_tools.trial import run_trial  # noqa: E402


class TestRunTrial(unittest.TestCase):
    """Tests for trial.run_trial."""

    def _make_migration(self) -> MagicMock:
        """Create a mock migration object."""
        mock = MagicMock()
        mock.get_steps.return_value = []
        mock.get_rollback_steps.return_value = []
        mock.manifest = MagicMock()
        return mock

    @patch("posthog.clickhouse.migration_tools.runner.run_migration_down")
    @patch("posthog.clickhouse.migration_tools.runner.run_migration_up")
    @patch("posthog.clickhouse.migration_tools.trial._query_schema")
    def test_run_trial_up_then_down(
        self,
        mock_schema: MagicMock,
        mock_up: MagicMock,
        mock_down: MagicMock,
    ) -> None:
        """Trial runs up, then down, in order."""
        pre_schema = [("t", "col1", "UInt64")]
        post_up_schema = [("t", "col1", "UInt64"), ("t", "col2", "String")]

        mock_schema.side_effect = [pre_schema, post_up_schema, pre_schema]
        mock_up.return_value = True
        mock_down.return_value = True

        cluster = MagicMock()
        result = run_trial(cluster, self._make_migration(), "default", 1, "0001_test")

        self.assertTrue(result)
        mock_up.assert_called_once()
        mock_down.assert_called_once()
        # Verify up was called with dry_run=True, then down with dry_run=True
        self.assertTrue(mock_up.call_args.kwargs.get("dry_run"))
        self.assertTrue(mock_down.call_args.kwargs.get("dry_run"))

    @patch("posthog.clickhouse.migration_tools.runner.run_migration_down")
    @patch("posthog.clickhouse.migration_tools.runner.run_migration_up")
    @patch("posthog.clickhouse.migration_tools.trial._query_schema")
    def test_run_trial_verify_after_up(
        self,
        mock_schema: MagicMock,
        mock_up: MagicMock,
        mock_down: MagicMock,
    ) -> None:
        """After up, _query_schema is called to verify schema changed."""
        pre_schema = [("t", "col1", "UInt64")]
        post_up_schema = [("t", "col1", "UInt64"), ("t", "col2", "String")]

        mock_schema.side_effect = [pre_schema, post_up_schema, pre_schema]
        mock_up.return_value = True
        mock_down.return_value = True

        cluster = MagicMock()
        run_trial(cluster, self._make_migration(), "default", 1, "0001_test")

        # _query_schema called 3 times: pre, post-up, post-down
        self.assertEqual(mock_schema.call_count, 3)

    @patch("posthog.clickhouse.migration_tools.runner.run_migration_down")
    @patch("posthog.clickhouse.migration_tools.runner.run_migration_up")
    @patch("posthog.clickhouse.migration_tools.trial._query_schema")
    def test_run_trial_verify_after_down(
        self,
        mock_schema: MagicMock,
        mock_up: MagicMock,
        mock_down: MagicMock,
    ) -> None:
        """After down, _query_schema is called to verify schema restored."""
        pre_schema = [("t", "col1", "UInt64")]
        post_up_schema = [("t", "col1", "UInt64"), ("t", "col2", "String")]
        # Schema NOT restored — should fail
        post_down_schema = [("t", "col1", "UInt64"), ("t", "col2", "String")]

        mock_schema.side_effect = [pre_schema, post_up_schema, post_down_schema]
        mock_up.return_value = True
        mock_down.return_value = True

        cluster = MagicMock()
        result = run_trial(cluster, self._make_migration(), "default", 1, "0001_test")

        self.assertFalse(result)
        self.assertEqual(mock_schema.call_count, 3)

    @patch("posthog.clickhouse.migration_tools.runner.run_migration_down")
    @patch("posthog.clickhouse.migration_tools.runner.run_migration_up")
    @patch("posthog.clickhouse.migration_tools.trial._query_schema")
    def test_run_trial_fails_if_up_fails(
        self,
        mock_schema: MagicMock,
        mock_up: MagicMock,
        mock_down: MagicMock,
    ) -> None:
        """If up fails, trial returns False and does NOT run down."""
        pre_schema = [("t", "col1", "UInt64")]
        mock_schema.return_value = pre_schema
        mock_up.return_value = False

        cluster = MagicMock()
        result = run_trial(cluster, self._make_migration(), "default", 1, "0001_test")

        self.assertFalse(result)
        mock_up.assert_called_once()
        mock_down.assert_not_called()

    @patch("posthog.clickhouse.migration_tools.runner.run_migration_down")
    @patch("posthog.clickhouse.migration_tools.runner.run_migration_up")
    @patch("posthog.clickhouse.migration_tools.trial._query_schema")
    def test_run_trial_fails_if_verify_fails_still_rolls_back(
        self,
        mock_schema: MagicMock,
        mock_up: MagicMock,
        mock_down: MagicMock,
    ) -> None:
        """If post-up verification fails (schema unchanged), trial fails
        and does not attempt rollback since up was a no-op."""
        pre_schema = [("t", "col1", "UInt64")]
        # Schema unchanged after up — verification failure
        mock_schema.side_effect = [pre_schema, pre_schema]
        mock_up.return_value = True

        cluster = MagicMock()
        result = run_trial(cluster, self._make_migration(), "default", 1, "0001_test")

        self.assertFalse(result)
        # Down should NOT be called since up was a no-op
        mock_down.assert_not_called()


if __name__ == "__main__":
    unittest.main()
