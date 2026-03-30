"""Unit tests for advisory locking in tracking.py.

Tests acquire_apply_lock and release_apply_lock with mocked ClickHouse
client — no Django or ClickHouse connection required.
"""

from __future__ import annotations

import os
import sys
import types
from collections.abc import Callable
from datetime import UTC, datetime

import unittest
from unittest.mock import MagicMock

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

    # Stub yaml so manifest.py can load without PyYAML
    sys.modules.setdefault("yaml", types.ModuleType("yaml"))

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from posthog.clickhouse.migration_tools.tracking import acquire_apply_lock, release_apply_lock  # noqa: E402


class TestAdvisoryLock(unittest.TestCase):
    """Tests for the advisory lock mechanism."""

    def test_advisory_lock_prevents_concurrent_apply(self) -> None:
        """An active lock from another host prevents acquisition."""
        client = MagicMock()
        now = datetime.now(tz=UTC)
        # Simulate existing lock from a different host
        client.execute.side_effect = [
            # First call: check for existing lock — returns a row
            [("other-pod", now)],
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod")

        self.assertFalse(acquired)
        self.assertIn("other-pod", reason)
        self.assertIn("--force", reason)

    def test_advisory_lock_expired_allows_apply(self) -> None:
        """No active lock (expired or absent) allows acquisition."""
        client = MagicMock()
        # First call: check for existing lock — returns empty (no active lock)
        # Second call: INSERT lock row
        client.execute.side_effect = [
            [],  # No active lock
            None,  # INSERT succeeds
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod")

        self.assertTrue(acquired)
        self.assertEqual(reason, "")
        # Should have called execute twice: SELECT check + INSERT lock
        self.assertEqual(client.execute.call_count, 2)

    def test_advisory_lock_same_host_allows_reacquire(self) -> None:
        """A lock from the same host allows re-acquisition (idempotent)."""
        client = MagicMock()
        now = datetime.now(tz=UTC)
        # Lock exists but from same host
        client.execute.side_effect = [
            [("my-pod", now)],  # Existing lock from same host
            None,  # INSERT lock row
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod")

        self.assertTrue(acquired)
        self.assertEqual(reason, "")

    def test_advisory_lock_force_overrides_other_host(self) -> None:
        """force=True acquires even when another host holds the lock."""
        client = MagicMock()
        # No SELECT should happen — force skips the check entirely.
        client.execute.side_effect = [
            None,  # INSERT lock row
        ]

        acquired, reason = acquire_apply_lock(client, "default", "my-pod", force=True)

        self.assertTrue(acquired)
        self.assertEqual(reason, "")
        # Only one call: the INSERT. No SELECT check.
        self.assertEqual(client.execute.call_count, 1)

    def test_release_apply_lock_inserts_shadow_row(self) -> None:
        """Release inserts a success=False row to shadow the lock."""
        client = MagicMock()
        client.execute.return_value = None

        release_apply_lock(client, "default", "my-pod")

        # Should have inserted a row (via record_step which calls client.execute)
        client.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
