from __future__ import annotations

from pathlib import Path

from unittest.mock import MagicMock, patch

import yaml

from posthog.clickhouse.migrations.manifest import ManifestStep, MigrationManifest

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_migration(tmp_path: Path, manifest_data: dict, sql_files: dict[str, str] | None = None) -> Path:
    """Create a migration directory with manifest.yaml and optional SQL files."""
    mig_dir = tmp_path / "0100_test_migration"
    mig_dir.mkdir(parents=True, exist_ok=True)
    (mig_dir / "manifest.yaml").write_text(yaml.dump(manifest_data))
    if sql_files:
        for name, content in sql_files.items():
            (mig_dir / name).write_text(content)
    return mig_dir


def _valid_manifest() -> dict:
    return {
        "description": "A valid test migration",
        "steps": [
            {"sql": "up.sql", "node_roles": ["DATA"], "comment": "create table"},
        ],
        "rollback": [
            {"sql": "down.sql", "node_roles": ["DATA"], "comment": "drop table"},
        ],
    }


# ---------------------------------------------------------------------------
# ValidationResult basics
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_validation_result_fields(self):
        from posthog.clickhouse.migrations.validator import ValidationResult

        r = ValidationResult(rule="test_rule", severity="error", message="something broke")
        assert r.rule == "test_rule"
        assert r.severity == "error"
        assert r.message == "something broke"

    def test_validation_result_warning(self):
        from posthog.clickhouse.migrations.validator import ValidationResult

        r = ValidationResult(rule="test_rule", severity="warning", message="heads up")
        assert r.severity == "warning"


# ---------------------------------------------------------------------------
# check_on_cluster
# ---------------------------------------------------------------------------


class TestCheckOnCluster:
    def test_detect_on_cluster(self):
        from posthog.clickhouse.migrations.validator import check_on_cluster

        sql = "CREATE TABLE foo ON CLUSTER '{cluster}' (id UInt64) ENGINE = MergeTree()"
        results = check_on_cluster(sql)
        assert len(results) == 1
        assert results[0].severity == "error"
        assert results[0].rule == "on_cluster"

    def test_detect_on_cluster_case_insensitive(self):
        from posthog.clickhouse.migrations.validator import check_on_cluster

        sql = "ALTER TABLE foo on cluster my_cluster ADD COLUMN bar String"
        results = check_on_cluster(sql)
        assert len(results) == 1
        assert results[0].severity == "error"

    def test_no_on_cluster_passes(self):
        from posthog.clickhouse.migrations.validator import check_on_cluster

        sql = "CREATE TABLE foo (id UInt64) ENGINE = MergeTree() ORDER BY id"
        results = check_on_cluster(sql)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# check_rollback_completeness
# ---------------------------------------------------------------------------


class TestCheckRollbackCompleteness:
    def test_detect_missing_rollback(self):
        from posthog.clickhouse.migrations.validator import check_rollback_completeness

        manifest = MigrationManifest(
            description="test",
            steps=[
                ManifestStep(sql="up.sql", node_roles=["DATA"]),
                ManifestStep(sql="up.sql#step2", node_roles=["DATA"]),
            ],
            rollback=[
                ManifestStep(sql="down.sql", node_roles=["DATA"]),
            ],
        )
        results = check_rollback_completeness(manifest)
        assert len(results) == 1
        assert results[0].severity == "error"
        assert results[0].rule == "rollback_completeness"
        assert "2 steps but 1 rollback" in results[0].message

    def test_matching_counts_passes(self):
        from posthog.clickhouse.migrations.validator import check_rollback_completeness

        manifest = MigrationManifest(
            description="test",
            steps=[ManifestStep(sql="up.sql", node_roles=["DATA"])],
            rollback=[ManifestStep(sql="down.sql", node_roles=["DATA"])],
        )
        results = check_rollback_completeness(manifest)
        assert len(results) == 0

    def test_empty_rollback_warns(self):
        from posthog.clickhouse.migrations.validator import check_rollback_completeness

        manifest = MigrationManifest(
            description="test",
            steps=[ManifestStep(sql="up.sql", node_roles=["DATA"])],
            rollback=[],
        )
        results = check_rollback_completeness(manifest)
        assert len(results) == 1
        assert results[0].severity == "error"


# ---------------------------------------------------------------------------
# check_node_role_consistency
# ---------------------------------------------------------------------------


class TestCheckNodeRoleConsistency:
    def test_detect_node_role_mismatch_sharded_on_coordinator(self):
        from posthog.clickhouse.migrations.validator import check_node_role_consistency

        manifest = MigrationManifest(
            description="test",
            steps=[
                ManifestStep(sql="up.sql", node_roles=["COORDINATOR"], sharded=True),
            ],
            rollback=[],
        )
        results = check_node_role_consistency(manifest)
        assert len(results) >= 1
        assert any(r.severity == "warning" and r.rule == "node_role_consistency" for r in results)

    def test_sharded_on_data_passes(self):
        from posthog.clickhouse.migrations.validator import check_node_role_consistency

        manifest = MigrationManifest(
            description="test",
            steps=[
                ManifestStep(sql="up.sql", node_roles=["DATA"], sharded=True),
            ],
            rollback=[],
        )
        results = check_node_role_consistency(manifest)
        assert len(results) == 0

    def test_non_sharded_any_role_passes(self):
        from posthog.clickhouse.migrations.validator import check_node_role_consistency

        manifest = MigrationManifest(
            description="test",
            steps=[
                ManifestStep(sql="up.sql", node_roles=["COORDINATOR"]),
            ],
            rollback=[],
        )
        results = check_node_role_consistency(manifest)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# check_drop_statements
# ---------------------------------------------------------------------------


class TestCheckDropStatements:
    def test_detect_drop_statement_warning(self):
        from posthog.clickhouse.migrations.validator import check_drop_statements

        sql = "DROP TABLE IF EXISTS posthog_test.my_table"
        results = check_drop_statements(sql, strict=False)
        assert len(results) == 1
        assert results[0].severity == "warning"
        assert results[0].rule == "drop_statement"

    def test_detect_drop_statement_strict(self):
        from posthog.clickhouse.migrations.validator import check_drop_statements

        sql = "DROP TABLE IF EXISTS posthog_test.my_table"
        results = check_drop_statements(sql, strict=True)
        assert len(results) == 1
        assert results[0].severity == "error"

    def test_no_drop_passes(self):
        from posthog.clickhouse.migrations.validator import check_drop_statements

        sql = "CREATE TABLE foo (id UInt64) ENGINE = MergeTree() ORDER BY id"
        results = check_drop_statements(sql, strict=False)
        assert len(results) == 0

    def test_drop_in_comment_ignored(self):
        from posthog.clickhouse.migrations.validator import check_drop_statements

        sql = "-- DROP TABLE old_table\nCREATE TABLE foo (id UInt64) ENGINE = MergeTree() ORDER BY id"
        results = check_drop_statements(sql, strict=False)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# check_companion_tables
# ---------------------------------------------------------------------------


class TestCheckCompanionTables:
    def test_detect_missing_companion_tables(self):
        from posthog.clickhouse.migrations.validator import check_companion_tables

        manifest = MigrationManifest(
            description="test",
            steps=[
                ManifestStep(
                    sql="up.sql",
                    node_roles=["DATA"],
                    sharded=True,
                ),
            ],
            rollback=[],
        )
        sql_content = "ALTER TABLE sharded_events ADD COLUMN foo String"
        results = check_companion_tables(manifest, sql_content)
        assert len(results) >= 1
        assert any(r.rule == "companion_tables" for r in results)

    def test_non_sharded_alter_no_warning(self):
        from posthog.clickhouse.migrations.validator import check_companion_tables

        manifest = MigrationManifest(
            description="test",
            steps=[
                ManifestStep(sql="up.sql", node_roles=["DATA"], sharded=False),
            ],
            rollback=[],
        )
        sql_content = "ALTER TABLE events ADD COLUMN foo String"
        results = check_companion_tables(manifest, sql_content)
        assert len(results) == 0

    def test_sharded_alter_with_companion_passes(self):
        from posthog.clickhouse.migrations.validator import check_companion_tables

        manifest = MigrationManifest(
            description="test",
            steps=[
                ManifestStep(sql="up.sql#alter_sharded", node_roles=["DATA"], sharded=True),
                ManifestStep(sql="up.sql#alter_kafka", node_roles=["DATA"]),
                ManifestStep(sql="up.sql#alter_mv", node_roles=["DATA"]),
                ManifestStep(sql="up.sql#alter_writable", node_roles=["DATA"]),
            ],
            rollback=[],
        )
        sql_content = (
            "-- @section: alter_sharded\n"
            "ALTER TABLE sharded_events ADD COLUMN foo String\n"
            "-- @section: alter_kafka\n"
            "ALTER TABLE kafka_events ADD COLUMN foo String\n"
            "-- @section: alter_mv\n"
            "ALTER TABLE events_mv MODIFY QUERY SELECT foo FROM kafka_events\n"
            "-- @section: alter_writable\n"
            "ALTER TABLE writable_events ADD COLUMN foo String\n"
        )
        results = check_companion_tables(manifest, sql_content)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# validate_migration (integration of all rules)
# ---------------------------------------------------------------------------


class TestValidateMigration:
    def test_validate_valid_migration(self, tmp_path):
        from posthog.clickhouse.migrations.validator import validate_migration

        mig_dir = _write_migration(
            tmp_path,
            _valid_manifest(),
            {
                "up.sql": "CREATE TABLE IF NOT EXISTS posthog_test.ch_migrate_test (id UInt64) ENGINE = MergeTree() ORDER BY id",
                "down.sql": "DROP TABLE IF EXISTS posthog_test.ch_migrate_test",
            },
        )
        results = validate_migration(mig_dir)
        errors = [r for r in results if r.severity == "error"]
        assert len(errors) == 0

    def test_validate_multiple_issues(self, tmp_path):
        from posthog.clickhouse.migrations.validator import validate_migration

        manifest_data = {
            "description": "bad migration",
            "steps": [
                {"sql": "up.sql", "node_roles": ["COORDINATOR"], "sharded": True},
            ],
            "rollback": [],
        }
        mig_dir = _write_migration(
            tmp_path,
            manifest_data,
            {
                "up.sql": "DROP TABLE foo ON CLUSTER '{cluster}'",
                "down.sql": "",
            },
        )
        results = validate_migration(mig_dir)
        rules = {r.rule for r in results}
        assert "on_cluster" in rules
        assert "rollback_completeness" in rules
        assert "node_role_consistency" in rules

    def test_validate_strict_mode(self, tmp_path):
        from posthog.clickhouse.migrations.validator import validate_migration

        mig_dir = _write_migration(
            tmp_path,
            _valid_manifest(),
            {
                "up.sql": "DROP TABLE IF EXISTS posthog_test.old_table",
                "down.sql": "CREATE TABLE posthog_test.old_table (id UInt64) ENGINE = MergeTree() ORDER BY id",
            },
        )
        results_normal = validate_migration(mig_dir, strict=False)
        results_strict = validate_migration(mig_dir, strict=True)
        normal_errors = [r for r in results_normal if r.severity == "error"]
        strict_errors = [r for r in results_strict if r.severity == "error"]
        assert len(strict_errors) > len(normal_errors)


# ---------------------------------------------------------------------------
# check_active_mutations
# ---------------------------------------------------------------------------


class TestCheckActiveMutations:
    @patch("posthog.clickhouse.migrations.runner._get_node_role_enum")
    @patch("posthog.clickhouse.migrations.runner._make_query", side_effect=lambda sql: sql)
    def test_check_active_mutations_returns_results(self, _mock_query, mock_role_enum):
        from posthog.clickhouse.migrations.runner import check_active_mutations

        mock_role_enum.return_value = lambda v: v

        cluster = MagicMock()
        mock_futures = MagicMock()
        # Simulate per-host results: host -> list of mutation rows
        mock_futures.result.return_value = {
            "host1": [
                {"table": "events", "mutation_id": "mut_001", "command": "ALTER TABLE events DELETE WHERE 1"},
            ],
        }
        cluster.map_hosts_by_roles.return_value = mock_futures

        results = check_active_mutations(cluster, "posthog", ["events"])
        assert len(results) >= 1
        assert results[0]["table"] == "events"

    @patch("posthog.clickhouse.migrations.runner._get_node_role_enum")
    @patch("posthog.clickhouse.migrations.runner._make_query", side_effect=lambda sql: sql)
    def test_check_active_mutations_empty(self, _mock_query, mock_role_enum):
        from posthog.clickhouse.migrations.runner import check_active_mutations

        mock_role_enum.return_value = lambda v: v

        cluster = MagicMock()
        mock_futures = MagicMock()
        mock_futures.result.return_value = {"host1": []}
        cluster.map_hosts_by_roles.return_value = mock_futures

        results = check_active_mutations(cluster, "posthog", ["events"])
        assert results == []

    @patch("posthog.clickhouse.migrations.runner._get_node_role_enum")
    @patch("posthog.clickhouse.migrations.runner._make_query", side_effect=lambda sql: sql)
    def test_check_active_mutations_queries_correct_tables(self, _mock_query, mock_role_enum):
        from posthog.clickhouse.migrations.runner import check_active_mutations

        mock_role_enum.return_value = lambda v: v

        cluster = MagicMock()
        mock_futures = MagicMock()
        mock_futures.result.return_value = {"host1": []}
        cluster.map_hosts_by_roles.return_value = mock_futures

        check_active_mutations(cluster, "posthog", ["events", "persons"])

        # Verify the SQL query was constructed with the table names
        call_args = cluster.map_hosts_by_roles.call_args
        query_sql = call_args[0][0]  # first positional arg is the query
        assert "events" in query_sql
        assert "persons" in query_sql


# ---------------------------------------------------------------------------
# First migration (0220) passes validation
# ---------------------------------------------------------------------------


class TestFirstMigrationValidation:
    def test_first_migration_passes_validation(self, tmp_path):
        from posthog.clickhouse.migrations.validator import validate_migration

        manifest_data = {
            "description": "Test new migration system",
            "steps": [
                {
                    "sql": "up.sql",
                    "node_roles": ["DATA"],
                    "comment": "create test table",
                },
            ],
            "rollback": [
                {
                    "sql": "down.sql",
                    "node_roles": ["DATA"],
                    "comment": "drop test table",
                },
            ],
        }
        mig_dir = _write_migration(
            tmp_path,
            manifest_data,
            {
                "up.sql": "CREATE TABLE IF NOT EXISTS posthog_test.ch_migrate_test (id UInt64) ENGINE = MergeTree() ORDER BY id",
                "down.sql": "DROP TABLE IF EXISTS posthog_test.ch_migrate_test",
            },
        )
        results = validate_migration(mig_dir)
        errors = [r for r in results if r.severity == "error"]
        assert len(errors) == 0

    def test_real_0220_migration_validates(self):
        from posthog.clickhouse.migrations.validator import validate_migration

        mig_dir = Path("posthog/clickhouse/migrations/0221_test_new_migration_system")
        if not mig_dir.exists():
            return
        results = validate_migration(mig_dir)
        errors = [r for r in results if r.severity == "error"]
        assert len(errors) == 0
