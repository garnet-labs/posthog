from pathlib import Path

from unittest.mock import MagicMock, patch

from posthog.clickhouse.migrations.manifest import ManifestStep

# ---------------------------------------------------------------------------
# run_migration_down
# ---------------------------------------------------------------------------


class TestRunMigrationDown:
    def _make_migration(self, rollback_steps=None):
        if rollback_steps is None:
            rollback_steps = [
                (
                    ManifestStep(sql="down.sql", node_roles=["DATA"]),
                    "DROP TABLE IF EXISTS test",
                ),
            ]

        migration = MagicMock()
        migration.get_rollback_steps.return_value = rollback_steps
        migration.get_steps.return_value = []
        migration.dir = Path("/fake")
        migration.manifest = MagicMock()
        migration.manifest.description = "test migration"
        return migration

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_run_migration_down_executes_rollback_steps(self, mock_execute, mock_record):
        from posthog.clickhouse.migrations.runner import run_migration_down

        mock_execute.return_value = {"host1": None}

        step = ManifestStep(sql="down.sql", node_roles=["DATA"])
        migration = self._make_migration(
            rollback_steps=[
                (step, "DROP TABLE IF EXISTS t1"),
                (ManifestStep(sql="down.sql#step2", node_roles=["DATA"]), "DROP TABLE IF EXISTS t2"),
            ]
        )

        result = run_migration_down(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        assert result is True
        assert mock_execute.call_count == 2

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_run_migration_down_records_tracking_with_direction_down(self, mock_execute, mock_record):
        from posthog.clickhouse.migrations.runner import run_migration_down

        mock_execute.return_value = {"host1": None}

        migration = self._make_migration()

        result = run_migration_down(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        assert result is True
        mock_record.assert_called()
        record_kwargs = mock_record.call_args[1]
        assert record_kwargs["direction"] == "down"
        assert record_kwargs["success"] is True

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_run_migration_down_halts_on_failure(self, mock_execute, mock_record):
        from posthog.clickhouse.migrations.runner import run_migration_down

        step1 = ManifestStep(sql="down.sql#step1", node_roles=["DATA"])
        step2 = ManifestStep(sql="down.sql#step2", node_roles=["DATA"])

        mock_execute.side_effect = [
            Exception("ClickHouse connection failed"),
        ]

        migration = self._make_migration(
            rollback_steps=[
                (step1, "DROP TABLE IF EXISTS t1"),
                (step2, "DROP TABLE IF EXISTS t2"),
            ]
        )

        result = run_migration_down(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        assert result is False
        # Step 2 should never have been attempted
        assert mock_execute.call_count == 1
        failure_calls = [c for c in mock_record.call_args_list if c[1].get("success") is False]
        assert len(failure_calls) >= 1

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_run_migration_down_records_per_host(self, mock_execute, mock_record):
        from posthog.clickhouse.migrations.runner import run_migration_down

        mock_execute.return_value = {"host1": None, "host2": None}

        migration = self._make_migration()
        run_migration_down(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_test",
        )

        assert mock_record.call_count == 2
        hosts_recorded = {c[1]["host"] for c in mock_record.call_args_list}
        assert hosts_recorded == {"host1", "host2"}

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_run_migration_down_returns_true_on_empty_rollback(self, mock_execute, mock_record):
        from posthog.clickhouse.migrations.runner import run_migration_down

        migration = self._make_migration(rollback_steps=[])

        result = run_migration_down(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        assert result is True
        mock_execute.assert_not_called()
        mock_record.assert_not_called()


# ---------------------------------------------------------------------------
# ch_migrate down command
# ---------------------------------------------------------------------------


class TestDownCommand:
    @patch("posthog.clickhouse.migrations.runner.discover_migrations")
    def test_down_command_finds_migration(self, mock_discover):
        from posthog.clickhouse.migrations.runner import discover_migrations

        mock_discover.return_value = [
            {"number": 1, "name": "0001_initial", "style": "new", "path": Path("/fake/0001_initial")},
            {"number": 2, "name": "0002_add_table", "style": "new", "path": Path("/fake/0002_add_table")},
        ]

        all_migs = discover_migrations()
        target_mig = next((m for m in all_migs if m["number"] == 2), None)
        assert target_mig is not None
        assert target_mig["name"] == "0002_add_table"

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_down_command_runs_rollback(self, mock_execute, mock_record):
        from posthog.clickhouse.migrations.runner import run_migration_down

        mock_execute.return_value = {"host1": None}

        migration = MagicMock()
        migration.get_rollback_steps.return_value = [
            (ManifestStep(sql="down.sql", node_roles=["DATA"]), "DROP TABLE IF EXISTS test"),
        ]

        result = run_migration_down(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=2,
            migration_name="0002_add_table",
        )

        assert result is True
        mock_execute.assert_called_once()
        record_kwargs = mock_record.call_args[1]
        assert record_kwargs["direction"] == "down"
        assert record_kwargs["migration_number"] == 2
