import re
import hashlib
from pathlib import Path

from unittest.mock import MagicMock, patch

import yaml

from posthog.clickhouse.migrations.manifest import ManifestStep

# ---------------------------------------------------------------------------
# discover_migrations
# ---------------------------------------------------------------------------


class TestDiscoverMigrations:
    def test_discover_migrations_finds_py_files(self, tmp_path):
        from posthog.clickhouse.migrations.runner import discover_migrations

        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "0001_initial.py").write_text("operations = []")
        (tmp_path / "0002_add_table.py").write_text("operations = []")
        (tmp_path / "helpers.py").write_text("")  # should be ignored

        result = discover_migrations(tmp_path)
        numbers = [m["number"] for m in result]
        assert numbers == [1, 2]
        assert all(m["style"] == "py" for m in result)

    def test_discover_migrations_finds_directories(self, tmp_path):
        from posthog.clickhouse.migrations.runner import discover_migrations

        (tmp_path / "__init__.py").write_text("")
        mig_dir = tmp_path / "0010_new_migration"
        mig_dir.mkdir()
        manifest = {
            "description": "test",
            "steps": [{"sql": "up.sql", "node_roles": ["DATA"]}],
        }
        (mig_dir / "manifest.yaml").write_text(yaml.dump(manifest))

        result = discover_migrations(tmp_path)
        assert len(result) == 1
        assert result[0]["number"] == 10
        assert result[0]["style"] == "new"

    def test_discover_migrations_sorts_by_number(self, tmp_path):
        from posthog.clickhouse.migrations.runner import discover_migrations

        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "0003_third.py").write_text("operations = []")
        (tmp_path / "0001_first.py").write_text("operations = []")

        mig_dir = tmp_path / "0002_second"
        mig_dir.mkdir()
        manifest = {
            "description": "second",
            "steps": [{"sql": "up.sql", "node_roles": ["DATA"]}],
        }
        (mig_dir / "manifest.yaml").write_text(yaml.dump(manifest))

        result = discover_migrations(tmp_path)
        numbers = [m["number"] for m in result]
        assert numbers == [1, 2, 3]

    def test_discover_migrations_ignores_dirs_without_manifest(self, tmp_path):
        from posthog.clickhouse.migrations.runner import discover_migrations

        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "0010_no_manifest").mkdir()

        result = discover_migrations(tmp_path)
        assert len(result) == 0

    def test_discover_migrations_ignores_pycache(self, tmp_path):
        from posthog.clickhouse.migrations.runner import discover_migrations

        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "0001_test.py").write_text("operations = []")

        result = discover_migrations(tmp_path)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# is_new_style
# ---------------------------------------------------------------------------


class TestIsNewStyle:
    def test_is_new_style_with_manifest(self, tmp_path):
        from posthog.clickhouse.migrations.runner import is_new_style

        mig_dir = tmp_path / "0010_test"
        mig_dir.mkdir()
        (mig_dir / "manifest.yaml").write_text("description: test\nsteps: []\n")

        assert is_new_style(mig_dir) is True

    def test_is_new_style_without_manifest(self, tmp_path):
        from posthog.clickhouse.migrations.runner import is_new_style

        mig_dir = tmp_path / "0010_test"
        mig_dir.mkdir()

        assert is_new_style(mig_dir) is False

    def test_is_new_style_py_file(self, tmp_path):
        from posthog.clickhouse.migrations.runner import is_new_style

        py_file = tmp_path / "0010_test.py"
        py_file.write_text("operations = []")

        assert is_new_style(py_file) is False


# ---------------------------------------------------------------------------
# compute_checksum
# ---------------------------------------------------------------------------


class TestComputeChecksum:
    def test_compute_checksum(self):
        from posthog.clickhouse.migrations.runner import compute_checksum

        sql = "CREATE TABLE test (id UInt64) ENGINE = MergeTree() ORDER BY id"
        expected = hashlib.sha256(sql.encode()).hexdigest()
        assert compute_checksum(sql) == expected

    def test_compute_checksum_is_sha256(self):
        from posthog.clickhouse.migrations.runner import compute_checksum

        result = compute_checksum("SELECT 1")
        assert re.match(r"^[a-f0-9]{64}$", result)

    def test_compute_checksum_deterministic(self):
        from posthog.clickhouse.migrations.runner import compute_checksum

        sql = "ALTER TABLE test ADD COLUMN foo String"
        assert compute_checksum(sql) == compute_checksum(sql)

    def test_compute_checksum_differs_for_different_sql(self):
        from posthog.clickhouse.migrations.runner import compute_checksum

        assert compute_checksum("SELECT 1") != compute_checksum("SELECT 2")


# ---------------------------------------------------------------------------
# execute_migration_step
# ---------------------------------------------------------------------------


def _fake_node_role(value):
    """Create a simple fake NodeRole-like value for testing without Django."""
    return value


class TestExecuteMigrationStep:
    def _make_step(self, *, sharded=False, is_alter_on_replicated_table=False, node_roles=None):
        return ManifestStep(
            sql="up.sql",
            node_roles=node_roles or ["DATA"],
            sharded=sharded,
            is_alter_on_replicated_table=is_alter_on_replicated_table,
        )

    @patch("posthog.clickhouse.migrations.runner._map_node_roles", return_value=["data"])
    @patch("posthog.clickhouse.migrations.runner._make_query", side_effect=lambda sql: sql)
    def test_execute_migration_step_sharded_replicated(self, mock_query, mock_roles):
        from posthog.clickhouse.migrations.runner import execute_migration_step

        cluster = MagicMock()
        mock_futures = MagicMock()
        mock_futures.result.return_value = {"host1": None}
        cluster.map_one_host_per_shard.return_value = mock_futures

        step = self._make_step(sharded=True, is_alter_on_replicated_table=True)
        result = execute_migration_step(cluster, step, "ALTER TABLE test ADD COLUMN x String")

        cluster.map_one_host_per_shard.assert_called_once()
        assert result == {"host1": None}

    @patch("posthog.clickhouse.migrations.runner._map_node_roles", return_value=["data"])
    @patch("posthog.clickhouse.migrations.runner._make_query", side_effect=lambda sql: sql)
    def test_execute_migration_step_replicated_only(self, mock_query, mock_roles):
        from posthog.clickhouse.migrations.runner import execute_migration_step

        cluster = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = None
        cluster.any_host_by_roles.return_value = mock_future

        step = self._make_step(is_alter_on_replicated_table=True)
        result = execute_migration_step(cluster, step, "ALTER TABLE test ADD COLUMN x String")

        cluster.any_host_by_roles.assert_called_once()
        assert isinstance(result, dict)

    @patch("posthog.clickhouse.migrations.runner._map_node_roles", return_value=["data"])
    @patch("posthog.clickhouse.migrations.runner._make_query", side_effect=lambda sql: sql)
    def test_execute_migration_step_default(self, mock_query, mock_roles):
        from posthog.clickhouse.migrations.runner import execute_migration_step

        cluster = MagicMock()
        mock_futures = MagicMock()
        mock_futures.result.return_value = {"host1": None, "host2": None}
        cluster.map_hosts_by_roles.return_value = mock_futures

        step = self._make_step()
        result = execute_migration_step(cluster, step, "CREATE TABLE test (id UInt64) ENGINE = MergeTree()")

        cluster.map_hosts_by_roles.assert_called_once()
        assert result == {"host1": None, "host2": None}

    @patch("posthog.clickhouse.migrations.runner._make_query", side_effect=lambda sql: sql)
    def test_execute_step_maps_uppercase_roles_to_node_role(self, mock_query):
        from posthog.clickhouse.migrations.runner import execute_migration_step

        cluster = MagicMock()
        mock_futures = MagicMock()
        mock_futures.result.return_value = {}
        cluster.map_hosts_by_roles.return_value = mock_futures

        step = self._make_step(node_roles=["DATA", "COORDINATOR"])

        # Mock _map_node_roles to return known values and verify it's called
        with patch(
            "posthog.clickhouse.migrations.runner._map_node_roles",
            return_value=["data", "coordinator"],
        ) as mock_map:
            execute_migration_step(cluster, step, "SELECT 1")
            mock_map.assert_called_once_with(["DATA", "COORDINATOR"])

        called_roles = cluster.map_hosts_by_roles.call_args[1].get(
            "node_roles",
            cluster.map_hosts_by_roles.call_args[0][1] if len(cluster.map_hosts_by_roles.call_args[0]) > 1 else None,
        )
        assert "data" in called_roles
        assert "coordinator" in called_roles


# ---------------------------------------------------------------------------
# run_migration_up
# ---------------------------------------------------------------------------


class TestRunMigrationUp:
    def _make_migration(self, tmp_path, steps_config=None):
        if steps_config is None:
            steps_config = [
                (
                    ManifestStep(sql="up.sql", node_roles=["DATA"]),
                    "CREATE TABLE test (id UInt64) ENGINE = MergeTree() ORDER BY id",
                ),
            ]

        migration = MagicMock()
        migration.get_steps.return_value = steps_config
        migration.dir = tmp_path
        migration.manifest = MagicMock()
        migration.manifest.description = "test migration"
        return migration

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_run_migration_up_records_tracking(self, mock_execute, mock_record, tmp_path):
        from posthog.clickhouse.migrations.runner import run_migration_up

        mock_execute.return_value = {"host1": None}

        migration = self._make_migration(tmp_path)
        result = run_migration_up(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        assert result is True
        mock_record.assert_called()
        record_kwargs = mock_record.call_args[1]
        assert record_kwargs["direction"] == "up"
        assert record_kwargs["success"] is True

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_run_migration_up_halts_on_failure(self, mock_execute, mock_record, tmp_path):
        from posthog.clickhouse.migrations.runner import run_migration_up

        step1 = ManifestStep(sql="up.sql#step1", node_roles=["DATA"])
        step2 = ManifestStep(sql="up.sql#step2", node_roles=["DATA"])

        mock_execute.side_effect = [
            Exception("ClickHouse connection failed"),
        ]

        migration = self._make_migration(
            tmp_path,
            steps_config=[
                (step1, "CREATE TABLE t1 (id UInt64) ENGINE = MergeTree() ORDER BY id"),
                (step2, "CREATE TABLE t2 (id UInt64) ENGINE = MergeTree() ORDER BY id"),
            ],
        )

        result = run_migration_up(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        assert result is False
        failure_calls = [c for c in mock_record.call_args_list if c[1].get("success") is False]
        assert len(failure_calls) >= 1
        # Step 2 should never have been attempted
        assert mock_execute.call_count == 1

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_run_migration_up_multiple_steps_all_succeed(self, mock_execute, mock_record, tmp_path):
        from posthog.clickhouse.migrations.runner import run_migration_up

        step1 = ManifestStep(sql="up.sql#step1", node_roles=["DATA"])
        step2 = ManifestStep(sql="up.sql#step2", node_roles=["COORDINATOR"])

        mock_execute.return_value = {"host1": None}

        migration = self._make_migration(
            tmp_path,
            steps_config=[
                (step1, "CREATE TABLE t1 (id UInt64) ENGINE = MergeTree() ORDER BY id"),
                (step2, "CREATE TABLE t2 (id UInt64) ENGINE = MergeTree() ORDER BY id"),
            ],
        )

        result = run_migration_up(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_test",
        )

        assert result is True
        assert mock_execute.call_count == 2
        # 2 step records + 1 migration-complete sentinel
        assert mock_record.call_count == 3
        # Verify the sentinel record
        sentinel_call = mock_record.call_args_list[-1]
        assert sentinel_call[1]["step_index"] == -1
        assert sentinel_call[1]["checksum"] == "complete"

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_run_migration_up_records_per_host(self, mock_execute, mock_record, tmp_path):
        from posthog.clickhouse.migrations.runner import run_migration_up

        mock_execute.return_value = {"host1": None, "host2": None}

        migration = self._make_migration(tmp_path)
        run_migration_up(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_test",
        )

        # 2 per-host records + 1 migration-complete sentinel
        assert mock_record.call_count == 3
        # Exclude sentinel (host="*") when checking per-host records
        hosts_recorded = {c[1]["host"] for c in mock_record.call_args_list if c[1]["host"] != "*"}
        assert hosts_recorded == {"host1", "host2"}


# ---------------------------------------------------------------------------
# get_pending_migrations
# ---------------------------------------------------------------------------


class TestGetPendingMigrations:
    @patch("posthog.clickhouse.migrations.runner.get_applied_migrations")
    @patch("posthog.clickhouse.migrations.runner.discover_migrations")
    def test_get_pending_excludes_applied(self, mock_discover, mock_applied):
        from posthog.clickhouse.migrations.runner import get_pending_migrations

        mock_discover.return_value = [
            {"number": 1, "name": "0001_initial", "style": "py", "path": Path("/fake")},
            {"number": 2, "name": "0002_add_table", "style": "new", "path": Path("/fake")},
            {"number": 3, "name": "0003_another", "style": "py", "path": Path("/fake")},
        ]
        mock_applied.return_value = [
            {"migration_number": 1, "migration_name": "0001_initial"},
            {"migration_number": 2, "migration_name": "0002_add_table"},
        ]

        client = MagicMock()
        result = get_pending_migrations(client, "test_db")

        assert len(result) == 1
        assert result[0]["number"] == 3

    @patch("posthog.clickhouse.migrations.runner.get_applied_migrations")
    @patch("posthog.clickhouse.migrations.runner.discover_migrations")
    def test_get_pending_returns_all_when_none_applied(self, mock_discover, mock_applied):
        from posthog.clickhouse.migrations.runner import get_pending_migrations

        mock_discover.return_value = [
            {"number": 1, "name": "0001_initial", "style": "py", "path": Path("/fake")},
        ]
        mock_applied.return_value = []

        client = MagicMock()
        result = get_pending_migrations(client, "test_db")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _ROLE_MAP coverage
# ---------------------------------------------------------------------------


class TestRoleMap:
    def test_role_map_has_expected_entries(self):
        from posthog.clickhouse.migrations.runner import _ROLE_MAP

        assert _ROLE_MAP["DATA"] == "data"
        assert _ROLE_MAP["COORDINATOR"] == "coordinator"
        assert _ROLE_MAP["INGESTION_EVENTS"] == "events"
        assert _ROLE_MAP["ALL"] == "all"

    def test_role_map_covers_valid_manifest_roles(self):
        from posthog.clickhouse.migrations.runner import _ROLE_MAP

        # The manifest currently validates DATA and COORDINATOR
        assert "DATA" in _ROLE_MAP
        assert "COORDINATOR" in _ROLE_MAP


# ---------------------------------------------------------------------------
# Concurrent execution guard (advisory lock)
# ---------------------------------------------------------------------------


class TestAcquireMigrationLock:
    def test_acquire_lock_succeeds_on_empty_table(self):
        from posthog.clickhouse.migrations.runner import acquire_migration_lock

        client = MagicMock()
        client.execute.return_value = None

        assert acquire_migration_lock(client, "test_db") is True
        client.execute.assert_called_once()
        call_args = client.execute.call_args
        assert "INSERT INTO test_db.clickhouse_schema_migrations" in call_args[0][0]

    def test_acquire_lock_fails_when_insert_raises(self):
        from posthog.clickhouse.migrations.runner import acquire_migration_lock

        client = MagicMock()
        client.execute.side_effect = Exception("Duplicate row")

        assert acquire_migration_lock(client, "test_db") is False


class TestReleaseMigrationLock:
    def test_release_lock_sends_delete(self):
        from posthog.clickhouse.migrations.runner import release_migration_lock

        client = MagicMock()
        release_migration_lock(client, "test_db")

        client.execute.assert_called_once()
        sql = client.execute.call_args[0][0]
        assert "DELETE FROM test_db.clickhouse_schema_migrations" in sql
        assert "step_index = -999" in sql

    def test_release_lock_does_not_raise_on_failure(self):
        from posthog.clickhouse.migrations.runner import release_migration_lock

        client = MagicMock()
        client.execute.side_effect = Exception("Network error")

        # Should not raise
        release_migration_lock(client, "test_db")


class TestCheckMigrationLock:
    def test_check_lock_returns_true_when_lock_exists(self):
        from posthog.clickhouse.migrations.runner import check_migration_lock

        client = MagicMock()
        client.execute.return_value = [(1,)]

        assert check_migration_lock(client, "test_db") is True

    def test_check_lock_returns_false_when_no_lock(self):
        from posthog.clickhouse.migrations.runner import check_migration_lock

        client = MagicMock()
        client.execute.return_value = [(0,)]

        assert check_migration_lock(client, "test_db") is False

    def test_check_lock_returns_false_on_exception(self):
        from posthog.clickhouse.migrations.runner import check_migration_lock

        client = MagicMock()
        client.execute.side_effect = Exception("Table not found")

        assert check_migration_lock(client, "test_db") is False


class TestAcquireMigrationLockWithRetry:
    @patch("posthog.clickhouse.migrations.runner.time.sleep")
    @patch("posthog.clickhouse.migrations.runner.acquire_migration_lock")
    @patch("posthog.clickhouse.migrations.runner.check_migration_lock")
    def test_acquires_on_first_attempt(self, mock_check, mock_acquire, mock_sleep):
        from posthog.clickhouse.migrations.runner import acquire_migration_lock_with_retry

        mock_check.return_value = False
        mock_acquire.return_value = True

        client = MagicMock()
        assert acquire_migration_lock_with_retry(client, "test_db") is True
        mock_sleep.assert_not_called()
        mock_acquire.assert_called_once()

    @patch("posthog.clickhouse.migrations.runner.time.sleep")
    @patch("posthog.clickhouse.migrations.runner.acquire_migration_lock")
    @patch("posthog.clickhouse.migrations.runner.check_migration_lock")
    def test_retries_when_lock_held(self, mock_check, mock_acquire, mock_sleep):
        from posthog.clickhouse.migrations.runner import acquire_migration_lock_with_retry

        # First two checks: lock held; third: lock free
        mock_check.side_effect = [True, True, False]
        mock_acquire.return_value = True

        client = MagicMock()
        assert acquire_migration_lock_with_retry(client, "test_db", max_attempts=3, retry_delay=0.01) is True
        assert mock_sleep.call_count == 2
        mock_acquire.assert_called_once()

    @patch("posthog.clickhouse.migrations.runner.time.sleep")
    @patch("posthog.clickhouse.migrations.runner.acquire_migration_lock")
    @patch("posthog.clickhouse.migrations.runner.check_migration_lock")
    def test_aborts_after_max_attempts(self, mock_check, mock_acquire, mock_sleep):
        from posthog.clickhouse.migrations.runner import acquire_migration_lock_with_retry

        mock_check.return_value = True  # Lock always held

        client = MagicMock()
        assert acquire_migration_lock_with_retry(client, "test_db", max_attempts=3, retry_delay=0.01) is False
        mock_acquire.assert_not_called()
        assert mock_sleep.call_count == 2  # max_attempts - 1

    @patch("posthog.clickhouse.migrations.runner.time.sleep")
    @patch("posthog.clickhouse.migrations.runner.acquire_migration_lock")
    @patch("posthog.clickhouse.migrations.runner.check_migration_lock")
    def test_retries_when_acquire_fails_despite_no_lock(self, mock_check, mock_acquire, mock_sleep):
        from posthog.clickhouse.migrations.runner import acquire_migration_lock_with_retry

        mock_check.return_value = False
        # First acquire fails (race condition), second succeeds
        mock_acquire.side_effect = [False, True]

        client = MagicMock()
        assert acquire_migration_lock_with_retry(client, "test_db", max_attempts=3, retry_delay=0.01) is True
        assert mock_acquire.call_count == 2


class TestLockConstants:
    def test_lock_step_index_is_sentinel(self):
        from posthog.clickhouse.migrations.runner import LOCK_STEP_INDEX

        assert LOCK_STEP_INDEX == -999

    def test_lock_migration_number_is_zero(self):
        from posthog.clickhouse.migrations.runner import LOCK_MIGRATION_NUMBER

        assert LOCK_MIGRATION_NUMBER == 0
