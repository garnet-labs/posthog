"""Unit tests for the migration tools parsing/validation layer.

Pattern 1: unittest.TestCase — no Django, no ClickHouse connection.
Tests parsing, validation, manifest logic, SQL rendering, and discovery.
"""

from __future__ import annotations

import os
import sys
import types
import hashlib
import tempfile
import textwrap
from pathlib import Path

import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub heavy dependencies so migration_tools can import without Django.
# Same pattern as test_deprecation.py.
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


_stubs_installed = False


def _install_stubs() -> None:
    global _stubs_installed
    if _stubs_installed:
        return
    _stubs_installed = True

    if _django_is_configured():
        return

    # posthog.celery — must be stubbed before posthog/__init__.py triggers
    _posthog_celery = types.ModuleType("posthog.celery")
    _posthog_celery.app = types.SimpleNamespace()  # type: ignore[attr-defined]
    sys.modules.setdefault("posthog.celery", _posthog_celery)

    fake_client = types.ModuleType("posthog.clickhouse.client")
    fake_client.__path__ = [os.path.join(_BASE, "posthog/clickhouse/client")]
    fake_client.__package__ = "posthog.clickhouse.client"
    sys.modules.setdefault("posthog.clickhouse.client", fake_client)

    fake_conn = types.ModuleType("posthog.clickhouse.client.connection")

    class NodeRole:
        DATA = "DATA"
        COORDINATOR = "COORDINATOR"
        ALL = "ALL"

    fake_conn.NodeRole = NodeRole  # type: ignore[attr-defined]
    sys.modules.setdefault("posthog.clickhouse.client.connection", fake_conn)

    fake_cluster = types.ModuleType("posthog.clickhouse.cluster")
    fake_cluster.Query = MagicMock()  # type: ignore[attr-defined]
    fake_cluster.get_cluster = MagicMock()  # type: ignore[attr-defined]
    sys.modules.setdefault("posthog.clickhouse.cluster", fake_cluster)

    for mod_name in ("infi", "infi.clickhouse_orm", "infi.clickhouse_orm.migrations"):
        m = types.ModuleType(mod_name)
        m.__path__ = ["/fake"]
        sys.modules.setdefault(mod_name, m)

    if not hasattr(sys.modules.get("infi.clickhouse_orm.migrations"), "RunPython"):

        class _FakeRunPython:
            def __init__(self, fn: object) -> None:
                pass

        sys.modules["infi.clickhouse_orm.migrations"].RunPython = _FakeRunPython  # type: ignore[attr-defined]

    fake_settings = types.ModuleType("posthog.settings")
    fake_settings.E2E_TESTING = False  # type: ignore[attr-defined]
    fake_settings.DEBUG = True  # type: ignore[attr-defined]
    fake_settings.CLOUD_DEPLOYMENT = False  # type: ignore[attr-defined]
    sys.modules.setdefault("posthog.settings", fake_settings)

    fake_ds = types.ModuleType("posthog.settings.data_stores")
    fake_ds.CLICKHOUSE_MIGRATIONS_CLUSTER = "default"  # type: ignore[attr-defined]
    fake_ds.CLICKHOUSE_MIGRATIONS_HOST = "localhost"  # type: ignore[attr-defined]
    sys.modules.setdefault("posthog.settings.data_stores", fake_ds)


_install_stubs()


# ---------------------------------------------------------------------------
# Manifest parsing tests
# ---------------------------------------------------------------------------


class TestParseManifest(unittest.TestCase):
    def _write_manifest(self, content: str) -> Path:
        d = tempfile.mkdtemp()
        p = Path(d) / "manifest.yaml"
        p.write_text(textwrap.dedent(content))
        return p

    def test_parse_manifest_valid(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import parse_manifest

        p = self._write_manifest("""\
            description: "Add column"
            steps:
              - sql: up.sql
                node_roles: ["DATA"]
            rollback:
              - sql: down.sql
                node_roles: ["DATA"]
        """)
        manifest = parse_manifest(p)
        self.assertEqual(manifest.description, "Add column")
        self.assertEqual(len(manifest.steps), 1)
        self.assertEqual(manifest.steps[0].sql, "up.sql")
        self.assertEqual(manifest.steps[0].node_roles, ["DATA"])
        self.assertEqual(len(manifest.rollback), 1)

    def test_parse_manifest_missing_steps(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import parse_manifest

        p = self._write_manifest("""\
            description: "No steps"
        """)
        with self.assertRaises(ValueError) as ctx:
            parse_manifest(p)
        self.assertIn("steps", str(ctx.exception))

    def test_parse_manifest_invalid_role(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import parse_manifest

        p = self._write_manifest("""\
            description: "Bad role"
            steps:
              - sql: up.sql
                node_roles: ["NONEXISTENT"]
            rollback: []
        """)
        with self.assertRaises(ValueError) as ctx:
            parse_manifest(p)
        self.assertIn("NONEXISTENT", str(ctx.exception))


# ---------------------------------------------------------------------------
# SQL section parser tests
# ---------------------------------------------------------------------------


class TestParseSqlSections(unittest.TestCase):
    def test_parse_sql_sections(self) -> None:
        from posthog.clickhouse.migration_tools.sql_parser import parse_sql_sections

        content = textwrap.dedent("""\
            -- @section: create_table
            CREATE TABLE foo (id UInt64) ENGINE = MergeTree() ORDER BY id;
            -- @section: add_column
            ALTER TABLE foo ADD COLUMN name String;
        """)
        sections = parse_sql_sections(content)
        self.assertIn("create_table", sections)
        self.assertIn("add_column", sections)
        self.assertIn("CREATE TABLE", sections["create_table"])
        self.assertIn("ALTER TABLE", sections["add_column"])

    def test_parse_sql_sections_duplicate(self) -> None:
        from posthog.clickhouse.migration_tools.sql_parser import parse_sql_sections

        content = textwrap.dedent("""\
            -- @section: same_name
            SELECT 1;
            -- @section: same_name
            SELECT 2;
        """)
        with self.assertRaises(ValueError) as ctx:
            parse_sql_sections(content)
        self.assertIn("Duplicate", str(ctx.exception))

    def test_parse_sql_sections_no_markers(self) -> None:
        from posthog.clickhouse.migration_tools.sql_parser import parse_sql_sections

        content = "SELECT 1;"
        sections = parse_sql_sections(content)
        self.assertIn("default", sections)
        self.assertEqual(sections["default"], "SELECT 1;")


# ---------------------------------------------------------------------------
# Jinja rendering tests
# ---------------------------------------------------------------------------


class TestRenderSql(unittest.TestCase):
    def test_render_sql_basic(self) -> None:
        from posthog.clickhouse.migration_tools.jinja_env import render_sql

        result = render_sql("CREATE TABLE {{ database }}.foo", {"database": "posthog"})
        self.assertEqual(result, "CREATE TABLE posthog.foo")

    def test_render_sql_rejects_block_tags(self) -> None:
        from posthog.clickhouse.migration_tools.jinja_env import render_sql

        with self.assertRaises(ValueError) as ctx:
            render_sql("{% if true %}SELECT 1{% endif %}", {})
        self.assertIn("block tags", str(ctx.exception))


# ---------------------------------------------------------------------------
# Validator rule tests
# ---------------------------------------------------------------------------


class TestValidatorRules(unittest.TestCase):
    def test_validate_migration_companion_tables(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import ManifestStep, MigrationManifest
        from posthog.clickhouse.migration_tools.validator import _check_companion_tables

        manifest = MigrationManifest(
            description="test",
            steps=[ManifestStep(sql="up.sql", node_roles=["DATA"], sharded=True)],
            rollback=[],
        )
        sql = "ALTER TABLE sharded_events ADD COLUMN foo String;"
        results = _check_companion_tables(manifest, sql)
        self.assertTrue(len(results) > 0)
        self.assertIn("companion", results[0].rule)

    def test_validate_migration_on_cluster_rejected(self) -> None:
        from posthog.clickhouse.migration_tools.validator import _check_on_cluster

        results = _check_on_cluster("CREATE TABLE foo ON CLUSTER 'default' (id UInt64)")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].severity, "error")
        self.assertIn("ON CLUSTER", results[0].message)

    def test_validate_migration_rollback_completeness(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import ManifestStep, MigrationManifest
        from posthog.clickhouse.migration_tools.validator import _check_rollback_completeness

        manifest = MigrationManifest(
            description="test",
            steps=[
                ManifestStep(sql="up.sql", node_roles=["DATA"]),
                ManifestStep(sql="up.sql#section2", node_roles=["DATA"]),
            ],
            rollback=[ManifestStep(sql="down.sql", node_roles=["DATA"])],
        )
        results = _check_rollback_completeness(manifest)
        self.assertEqual(len(results), 1)
        self.assertIn("2 steps but 1 rollback", results[0].message)


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


class TestDiscoverMigrations(unittest.TestCase):
    def test_discover_migrations(self) -> None:
        from posthog.clickhouse.migration_tools.runner import discover_migrations

        d = Path(tempfile.mkdtemp())

        # Create a .py migration
        (d / "0001_initial.py").write_text("# migration")

        # Create a directory-based migration
        mig_dir = d / "0002_add_column"
        mig_dir.mkdir()
        (mig_dir / "manifest.yaml").write_text("description: test\nsteps: []\nrollback: []")

        # Should skip non-migration files
        (d / "__init__.py").write_text("")
        (d / "README.md").write_text("docs")

        migrations = discover_migrations(d)
        self.assertEqual(len(migrations), 2)
        self.assertEqual(migrations[0]["number"], 1)
        self.assertEqual(migrations[0]["style"], "py")
        self.assertEqual(migrations[1]["number"], 2)
        self.assertEqual(migrations[1]["style"], "new")


# ---------------------------------------------------------------------------
# Checksum tests
# ---------------------------------------------------------------------------


class TestComputeChecksum(unittest.TestCase):
    def test_compute_checksum_deterministic(self) -> None:
        from posthog.clickhouse.migration_tools.runner import compute_checksum

        sql = "ALTER TABLE foo ADD COLUMN bar String;"
        c1 = compute_checksum(sql)
        c2 = compute_checksum(sql)
        self.assertEqual(c1, c2)
        self.assertEqual(c1, hashlib.sha256(sql.encode()).hexdigest())

    def test_compute_checksum_differs_for_different_sql(self) -> None:
        from posthog.clickhouse.migration_tools.runner import compute_checksum

        self.assertNotEqual(compute_checksum("SELECT 1"), compute_checksum("SELECT 2"))


# ---------------------------------------------------------------------------
# Pending migrations test (with mocked CH client)
# ---------------------------------------------------------------------------


class TestGetPendingMigrations(unittest.TestCase):
    def test_get_pending_migrations_excludes_applied(self) -> None:
        from posthog.clickhouse.migration_tools.runner import get_pending_migrations

        d = Path(tempfile.mkdtemp())
        (d / "0001_initial.py").write_text("# migration")
        (d / "0002_add_col.py").write_text("# migration")

        mock_client = MagicMock()
        # Simulate migration 1 as applied (has complete sentinel)
        mock_client.execute.return_value = [
            (1, "0001_initial", -1, "*", "*", "up", "complete", "2024-01-01", True),
        ]

        pending = get_pending_migrations(mock_client, "default", migrations_dir=d)
        numbers = [m["number"] for m in pending]
        self.assertNotIn(1, numbers)
        self.assertIn(2, numbers)


# ---------------------------------------------------------------------------
# Advisory lock tests
# ---------------------------------------------------------------------------


class TestAdvisoryLock(unittest.TestCase):
    """Tests for acquire_apply_lock / release_apply_lock in tracking.py."""

    def test_advisory_lock_prevents_concurrent_apply(self) -> None:
        """If another host holds a recent lock, acquire returns False."""
        from datetime import UTC, datetime, timedelta

        from posthog.clickhouse.migration_tools.tracking import acquire_apply_lock

        mock_client = MagicMock()
        # Simulate an existing lock from a different host within the last 30 minutes
        lock_time = datetime.now(tz=UTC) - timedelta(minutes=5)
        mock_client.execute.return_value = [("other-host", lock_time)]

        acquired, reason = acquire_apply_lock(mock_client, "default", "my-host")

        self.assertFalse(acquired)
        self.assertIn("other-host", reason)
        self.assertIn("--force", reason)

    def test_advisory_lock_expired_allows_apply(self) -> None:
        """If no recent lock exists, acquire succeeds."""
        from posthog.clickhouse.migration_tools.tracking import acquire_apply_lock

        mock_client = MagicMock()
        # No rows returned = no active lock
        mock_client.execute.return_value = []

        acquired, reason = acquire_apply_lock(mock_client, "default", "my-host")

        self.assertTrue(acquired)
        self.assertEqual(reason, "")
        # Should have called execute twice: once for check, once for insert (via record_step)
        self.assertGreaterEqual(mock_client.execute.call_count, 2)

    def test_advisory_lock_same_host_allows_reacquire(self) -> None:
        """If the same host holds the lock, acquire succeeds (re-entrant)."""
        from datetime import UTC, datetime, timedelta

        from posthog.clickhouse.migration_tools.tracking import acquire_apply_lock

        mock_client = MagicMock()
        lock_time = datetime.now(tz=UTC) - timedelta(minutes=5)
        mock_client.execute.return_value = [("my-host", lock_time)]

        acquired, reason = acquire_apply_lock(mock_client, "default", "my-host")

        self.assertTrue(acquired)
        self.assertEqual(reason, "")

    def test_release_apply_lock_inserts_shadow_row(self) -> None:
        """release_apply_lock inserts a success=False row to shadow the lock."""
        from posthog.clickhouse.migration_tools.tracking import release_apply_lock

        mock_client = MagicMock()
        release_apply_lock(mock_client, "default", "my-host")

        # Should have called execute (via record_step) with the unlock record
        mock_client.execute.assert_called_once()
        call_args = mock_client.execute.call_args
        # The params tuple should contain success=False
        params = call_args[0][1][0]  # second positional arg, first tuple in list
        # success is the last element in the params tuple
        self.assertFalse(params[-1])


if __name__ == "__main__":
    unittest.main()
