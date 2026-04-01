"""Unit tests for the ClickHouse migration runner.

Tests run_migration_up, run_migration_down, and execute_migration_step
with mocked ClickhouseCluster — no Django or ClickHouse connection required.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import posthog.clickhouse.test._stubs  # noqa: F401
from posthog.clickhouse.migration_tools.manifest import ManifestStep, MigrationManifest
from posthog.clickhouse.migration_tools.runner import execute_migration_step, run_migration_down, run_migration_up
from posthog.clickhouse.migration_tools.tracking import MIGRATION_COMPLETE_STEP


def _make_step(
    sql: str = "up.sql",
    node_roles: list[str] | None = None,
    sharded: bool = False,
    is_alter_on_replicated_table: bool = False,
) -> ManifestStep:
    return ManifestStep(
        sql=sql,
        node_roles=node_roles or ["DATA"],
        sharded=sharded,
        is_alter_on_replicated_table=is_alter_on_replicated_table,
    )


def _make_migration(steps: list[ManifestStep], rollback: list[ManifestStep] | None = None):
    """Create a mock migration object with get_steps() / get_rollback_steps()."""
    manifest = MigrationManifest(description="test", steps=steps, rollback=rollback or [])
    mock = MagicMock()
    mock.manifest = manifest
    mock.get_steps.return_value = [(s, f"SQL for {s.sql}") for s in steps]
    mock.get_rollback_steps.return_value = [(s, f"ROLLBACK SQL for {s.sql}") for s in (rollback or [])]
    return mock


class TestExecuteMigrationStep(unittest.TestCase):
    """Tests for runner.execute_migration_step routing logic."""

    def test_execute_migration_step_normal(self) -> None:
        """Normal steps (no sharded, no alter) use map_hosts_by_roles."""
        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.return_value = {("host1", 9000): []}

        step = _make_step()
        result = execute_migration_step(cluster, step, "SELECT 1")

        cluster.map_hosts_by_roles.assert_called_once()
        self.assertIn(("host1", 9000), result)

    def test_execute_migration_step_sharded_alter(self) -> None:
        """Sharded + alter uses map_one_host_per_shard."""
        cluster = MagicMock()
        cluster.map_one_host_per_shard.return_value.result.return_value = {("shard1", 9000): []}

        step = _make_step(sharded=True, is_alter_on_replicated_table=True)
        result = execute_migration_step(cluster, step, "ALTER TABLE foo ADD COLUMN x UInt64")

        cluster.map_one_host_per_shard.assert_called_once()
        self.assertIn(("shard1", 9000), result)

    def test_execute_migration_step_alter_replicated(self) -> None:
        """Alter-only (not sharded) uses any_host_by_roles."""
        cluster = MagicMock()
        cluster.any_host_by_roles.return_value.result.return_value = "ok"

        step = _make_step(is_alter_on_replicated_table=True)
        result = execute_migration_step(cluster, step, "ALTER TABLE foo ADD COLUMN x UInt64")

        cluster.any_host_by_roles.assert_called_once()
        self.assertEqual(result, {"single_host": "ok"})


class TestRunMigrationUp(unittest.TestCase):
    """Tests for runner.run_migration_up."""

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    @patch("posthog.clickhouse.client.migration_tools.get_migrations_cluster")
    def test_run_migration_up_all_steps_succeed(self, mock_get_cluster: MagicMock, mock_record: MagicMock) -> None:
        """Successful run records step results and a completion sentinel."""
        # Setup tracking cluster to return empty prior results
        mock_tracking = MagicMock()
        mock_tracking.any_host.return_value.result.return_value = {}
        mock_get_cluster.return_value = mock_tracking

        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.return_value = {("host1", 9000): []}

        steps = [_make_step(sql="up.sql")]
        migration = _make_migration(steps)

        success = run_migration_up(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
        )

        self.assertTrue(success)

        # Should have recorded: step 0 success + completion sentinel
        calls = mock_record.call_args_list
        self.assertTrue(len(calls) >= 2)

        # Last call should be the completion sentinel
        last_call = calls[-1]
        self.assertEqual(last_call.kwargs["record"].step_index, MIGRATION_COMPLETE_STEP)
        self.assertEqual(last_call.kwargs["record"].checksum, "complete")

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    def test_run_migration_up_step_fails_no_sentinel(self, mock_record: MagicMock) -> None:
        """When a step fails, no completion sentinel is written."""
        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.side_effect = Exception("CH error")

        steps = [_make_step(sql="up.sql")]
        migration = _make_migration(steps)

        success = run_migration_up(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
        )

        self.assertFalse(success)

        # Should have recorded failure but no completion sentinel
        for call in mock_record.call_args_list:
            self.assertNotEqual(call.kwargs["record"].step_index, MIGRATION_COMPLETE_STEP)

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    def test_run_migration_up_step_fails_records_failure(self, mock_record: MagicMock) -> None:
        """A failed step is recorded with success=False."""
        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.side_effect = Exception("CH error")

        steps = [_make_step(sql="up.sql")]
        migration = _make_migration(steps)

        run_migration_up(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
        )

        # Find the failure record
        failure_calls = [c for c in mock_record.call_args_list if c.kwargs["record"].success is False]
        self.assertTrue(len(failure_calls) >= 1)
        self.assertEqual(failure_calls[0].kwargs["record"].step_index, 0)


class TestRunMigrationDown(unittest.TestCase):
    """Tests for runner.run_migration_down."""

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    def test_run_migration_down_executes_rollback_steps(self, mock_record: MagicMock) -> None:
        """Rollback steps execute in order and record direction='down'."""
        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.return_value = {("host1", 9000): []}

        rollback = [_make_step(sql="down.sql")]
        migration = _make_migration(steps=[_make_step()], rollback=rollback)

        success = run_migration_down(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
        )

        self.assertTrue(success)

        # All records should have direction='down'
        for call in mock_record.call_args_list:
            self.assertEqual(call.kwargs["record"].direction, "down")


class TestDryRun(unittest.TestCase):
    """Tests for the dry_run flag on run_migration_up and run_migration_down."""

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    def test_dry_run_up_skips_all_tracking(self, mock_record: MagicMock) -> None:
        """dry_run=True executes SQL but writes nothing to the tracking table."""
        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.return_value = {("host1", 9000): []}

        steps = [_make_step(sql="up.sql")]
        migration = _make_migration(steps)

        success = run_migration_up(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
            dry_run=True,
        )

        self.assertTrue(success)
        # SQL was executed
        cluster.map_hosts_by_roles.assert_called_once()
        # No tracking records written
        mock_record.assert_not_called()

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    def test_dry_run_up_failure_skips_tracking(self, mock_record: MagicMock) -> None:
        """dry_run=True skips tracking even on failure."""
        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.side_effect = Exception("CH error")

        steps = [_make_step(sql="up.sql")]
        migration = _make_migration(steps)

        success = run_migration_up(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
            dry_run=True,
        )

        self.assertFalse(success)
        mock_record.assert_not_called()

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    def test_dry_run_down_skips_all_tracking(self, mock_record: MagicMock) -> None:
        """dry_run=True on rollback executes SQL but writes nothing."""
        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.return_value = {("host1", 9000): []}

        rollback = [_make_step(sql="down.sql")]
        migration = _make_migration(steps=[_make_step()], rollback=rollback)

        success = run_migration_down(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
            dry_run=True,
        )

        self.assertTrue(success)
        cluster.map_hosts_by_roles.assert_called_once()
        mock_record.assert_not_called()


class TestRollbackSentinel(unittest.TestCase):
    """Tests for the rollback-complete sentinel in run_migration_down."""

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    def test_successful_rollback_writes_down_sentinel(self, mock_record: MagicMock) -> None:
        """A successful rollback writes a down-sentinel (step_index=-1, direction='down')."""
        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.return_value = {("host1", 9000): []}

        rollback = [_make_step(sql="down.sql")]
        migration = _make_migration(steps=[_make_step()], rollback=rollback)

        success = run_migration_down(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
        )

        self.assertTrue(success)

        # Last call should be the rollback-complete sentinel
        calls = mock_record.call_args_list
        self.assertTrue(len(calls) >= 2)
        last_call = calls[-1]
        self.assertEqual(last_call.kwargs["record"].step_index, MIGRATION_COMPLETE_STEP)
        self.assertEqual(last_call.kwargs["record"].direction, "down")
        self.assertEqual(last_call.kwargs["record"].checksum, "rollback")

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    def test_failed_rollback_no_down_sentinel(self, mock_record: MagicMock) -> None:
        """A failed rollback does not write a down-sentinel."""
        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.side_effect = Exception("CH error")

        rollback = [_make_step(sql="down.sql")]
        migration = _make_migration(steps=[_make_step()], rollback=rollback)

        success = run_migration_down(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
        )

        self.assertFalse(success)

        # No sentinel should be written
        for call in mock_record.call_args_list:
            self.assertNotEqual(call.kwargs["record"].step_index, MIGRATION_COMPLETE_STEP)

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    def test_rollback_that_drops_tracking_table_skips_tracking_writes(self, mock_record: MagicMock) -> None:
        """Dropping the tracking table should not try to record rollback rows afterward."""
        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.return_value = {("host1", 9000): []}

        rollback_step = _make_step(sql="down.sql")
        migration = MagicMock()
        migration.get_rollback_steps.return_value = [
            (rollback_step, "DROP TABLE IF EXISTS default.clickhouse_schema_migrations"),
        ]

        success = run_migration_down(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=224,
            migration_name="0224_ch_migrate_bootstrap",
        )

        self.assertTrue(success)
        mock_record.assert_not_called()


class TestPerHostRetry(unittest.TestCase):
    """Tests for per-host step-level retry in run_migration_up."""

    def _setup_tracking_cluster(self, prior_results: dict) -> MagicMock:
        """Create a mock tracking cluster that returns prior_results via any_host."""
        mock_tracking_cluster = MagicMock()

        def _any_host_side_effect(fn: object) -> MagicMock:
            future = MagicMock()
            future.result.return_value = prior_results
            return future

        mock_tracking_cluster.any_host.side_effect = _any_host_side_effect
        return mock_tracking_cluster

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    @patch("posthog.clickhouse.client.migration_tools.get_migrations_cluster")
    def test_run_migration_up_skips_already_applied_hosts(
        self,
        mock_get_cluster: MagicMock,
        mock_record: MagicMock,
    ) -> None:
        """Re-running a migration skips recording for hosts that already succeeded."""
        # Step 0 already succeeded on host1
        prior = {(0, "('host1', 9000)"): True}
        mock_get_cluster.return_value = self._setup_tracking_cluster(prior)

        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.return_value = {
            ("host1", 9000): [],
            ("host2", 9000): [],
        }

        steps = [_make_step(sql="step0.sql"), _make_step(sql="step1.sql")]
        migration = _make_migration(steps)

        success = run_migration_up(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
        )

        self.assertTrue(success)

        # Check that step 0 only recorded for host2 (host1 was already applied)
        step0_records = [
            c
            for c in mock_record.call_args_list
            if c.kwargs["record"].step_index == 0 and c.kwargs["record"].success is True
        ]
        step0_hosts = [c.kwargs["record"].host for c in step0_records]
        self.assertIn("('host2', 9000)", step0_hosts)
        self.assertNotIn("('host1', 9000)", step0_hosts)

        # Step 1 should record for both hosts (no prior results for step 1)
        step1_records = [
            c
            for c in mock_record.call_args_list
            if c.kwargs["record"].step_index == 1 and c.kwargs["record"].success is True
        ]
        self.assertEqual(len(step1_records), 2)

    @patch("posthog.clickhouse.migration_tools.runner._record_for_tracking")
    @patch("posthog.clickhouse.client.migration_tools.get_migrations_cluster")
    def test_run_migration_up_full_retry_after_complete_step_failure(
        self,
        mock_get_cluster: MagicMock,
        mock_record: MagicMock,
    ) -> None:
        """With no prior results, all steps execute on all hosts."""
        mock_get_cluster.return_value = self._setup_tracking_cluster({})

        cluster = MagicMock()
        cluster.map_hosts_by_roles.return_value.result.return_value = {
            ("host1", 9000): [],
            ("host2", 9000): [],
        }

        steps = [_make_step(sql="step0.sql"), _make_step(sql="step1.sql")]
        migration = _make_migration(steps)

        success = run_migration_up(
            cluster=cluster,
            migration=migration,
            database="default",
            migration_number=1,
            migration_name="0001_test",
        )

        self.assertTrue(success)

        # Both steps should have records for both hosts
        for step_idx in (0, 1):
            step_records = [
                c
                for c in mock_record.call_args_list
                if c.kwargs["record"].step_index == step_idx and c.kwargs["record"].success is True
            ]
            self.assertEqual(len(step_records), 2, f"Step {step_idx} should have 2 host records")


if __name__ == "__main__":
    unittest.main()
