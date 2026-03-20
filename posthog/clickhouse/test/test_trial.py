from pathlib import Path

from unittest.mock import MagicMock, patch

from posthog.clickhouse.migrations.manifest import ManifestStep

# ---------------------------------------------------------------------------
# run_trial
# ---------------------------------------------------------------------------


def _make_migration(up_steps=None, rollback_steps=None):
    if up_steps is None:
        up_steps = [
            (
                ManifestStep(sql="up.sql", node_roles=["DATA"]),
                "ALTER TABLE test ADD COLUMN foo String",
            ),
        ]
    if rollback_steps is None:
        rollback_steps = [
            (
                ManifestStep(sql="down.sql", node_roles=["DATA"]),
                "ALTER TABLE test DROP COLUMN foo",
            ),
        ]

    migration = MagicMock()
    migration.get_steps.return_value = up_steps
    migration.get_rollback_steps.return_value = rollback_steps
    migration.dir = Path("/fake")
    migration.manifest = MagicMock()
    migration.manifest.description = "test migration"
    return migration


class TestRunTrial:
    @patch("posthog.clickhouse.migrations.trial._query_schema")
    @patch("posthog.clickhouse.migrations.runner.run_migration_down")
    @patch("posthog.clickhouse.migrations.runner.run_migration_up")
    def test_trial_runs_up_then_down(self, mock_up, mock_down, mock_schema):
        from posthog.clickhouse.migrations.trial import run_trial

        mock_up.return_value = True
        mock_down.return_value = True
        # Pre-migration schema and post-rollback schema match
        schema_snapshot = [("test", "id", "UInt64")]
        mock_schema.return_value = schema_snapshot

        migration = _make_migration()

        result = run_trial(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        assert result is True
        mock_up.assert_called_once()
        mock_down.assert_called_once()

    @patch("posthog.clickhouse.migrations.trial._query_schema")
    @patch("posthog.clickhouse.migrations.runner.run_migration_down")
    @patch("posthog.clickhouse.migrations.runner.run_migration_up")
    def test_trial_fails_if_up_fails(self, mock_up, mock_down, mock_schema):
        from posthog.clickhouse.migrations.trial import run_trial

        mock_up.return_value = False
        schema_snapshot = [("test", "id", "UInt64")]
        mock_schema.return_value = schema_snapshot

        migration = _make_migration()

        result = run_trial(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        assert result is False
        mock_down.assert_not_called()

    @patch("posthog.clickhouse.migrations.trial._query_schema")
    @patch("posthog.clickhouse.migrations.runner.run_migration_down")
    @patch("posthog.clickhouse.migrations.runner.run_migration_up")
    def test_trial_fails_if_down_fails(self, mock_up, mock_down, mock_schema):
        from posthog.clickhouse.migrations.trial import run_trial

        mock_up.return_value = True
        mock_down.return_value = False
        schema_snapshot = [("test", "id", "UInt64")]
        mock_schema.return_value = schema_snapshot

        migration = _make_migration()

        result = run_trial(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        assert result is False

    @patch("posthog.clickhouse.migrations.trial._query_schema")
    @patch("posthog.clickhouse.migrations.runner.run_migration_down")
    @patch("posthog.clickhouse.migrations.runner.run_migration_up")
    def test_trial_fails_if_schema_not_restored(self, mock_up, mock_down, mock_schema):
        from posthog.clickhouse.migrations.trial import run_trial

        mock_up.return_value = True
        mock_down.return_value = True

        # Schema changes between calls: pre-migration differs from post-rollback
        pre_schema = [("test", "id", "UInt64")]
        post_schema = [("test", "id", "UInt64"), ("test", "foo", "String")]
        mock_schema.side_effect = [pre_schema, post_schema]

        migration = _make_migration()

        result = run_trial(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        assert result is False

    @patch("posthog.clickhouse.migrations.trial._query_schema")
    @patch("posthog.clickhouse.migrations.runner.run_migration_down")
    @patch("posthog.clickhouse.migrations.runner.run_migration_up")
    def test_trial_captures_schema_before(self, mock_up, mock_down, mock_schema):
        from posthog.clickhouse.migrations.trial import run_trial

        mock_up.return_value = True
        mock_down.return_value = True
        schema_snapshot = [("test", "id", "UInt64")]
        mock_schema.return_value = schema_snapshot

        migration = _make_migration()
        cluster = MagicMock()

        run_trial(
            cluster=cluster,
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_initial",
        )

        # _query_schema should be called at least twice: before up and after down
        assert mock_schema.call_count >= 2
