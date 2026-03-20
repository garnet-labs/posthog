from __future__ import annotations

from pathlib import Path

from unittest.mock import MagicMock, patch

import yaml

from posthog.clickhouse.migrations.manifest import ManifestStep, MigrationManifest, parse_manifest

# ---------------------------------------------------------------------------
# Manifest parsing: per-step clusters
# ---------------------------------------------------------------------------


class TestManifestWithPerStepClusters:
    def test_manifest_with_per_step_clusters(self, tmp_path: Path) -> None:
        manifest_yaml = {
            "description": "Per-step cluster targeting",
            "steps": [
                {
                    "sql": "up.sql#step1",
                    "node_roles": ["DATA"],
                    "clusters": ["us-east", "eu-west"],
                },
                {
                    "sql": "up.sql#step2",
                    "node_roles": ["COORDINATOR"],
                    "clusters": ["us-east"],
                },
            ],
            "rollback": [],
        }
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(manifest_yaml))

        result = parse_manifest(manifest_file)

        assert result.steps[0].clusters == ["us-east", "eu-west"]
        assert result.steps[1].clusters == ["us-east"]
        assert result.clusters is None

    def test_manifest_with_global_cluster(self, tmp_path: Path) -> None:
        manifest_yaml = {
            "description": "Global cluster config",
            "cluster": "posthog",
            "steps": [
                {
                    "sql": "up.sql",
                    "node_roles": ["DATA"],
                },
            ],
            "rollback": [],
        }
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(manifest_yaml))

        result = parse_manifest(manifest_file)

        assert result.cluster == "posthog"
        assert result.clusters is None
        assert result.steps[0].clusters is None

    def test_manifest_with_global_clusters_list(self, tmp_path: Path) -> None:
        manifest_yaml = {
            "description": "Global clusters list",
            "clusters": ["us-east", "eu-west"],
            "steps": [
                {
                    "sql": "up.sql",
                    "node_roles": ["DATA"],
                },
            ],
            "rollback": [],
        }
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(manifest_yaml))

        result = parse_manifest(manifest_file)

        assert result.clusters == ["us-east", "eu-west"]
        assert result.steps[0].clusters is None

    def test_step_clusters_override_global(self, tmp_path: Path) -> None:
        manifest_yaml = {
            "description": "Step override of global clusters",
            "clusters": ["us-east", "eu-west", "ap-south"],
            "steps": [
                {
                    "sql": "up.sql#step1",
                    "node_roles": ["DATA"],
                    "clusters": ["us-east"],
                },
                {
                    "sql": "up.sql#step2",
                    "node_roles": ["DATA"],
                },
            ],
            "rollback": [],
        }
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(manifest_yaml))

        result = parse_manifest(manifest_file)

        # Step 1 has explicit override
        assert result.steps[0].clusters == ["us-east"]
        # Step 2 inherits None — resolved at runtime from manifest.clusters
        assert result.steps[1].clusters is None


# ---------------------------------------------------------------------------
# resolve_step_clusters helper
# ---------------------------------------------------------------------------


class TestResolveStepClusters:
    def test_step_clusters_takes_precedence(self) -> None:
        from posthog.clickhouse.migrations.runner import resolve_step_clusters

        manifest = MigrationManifest(
            description="test",
            steps=[],
            rollback=[],
            clusters=["us-east", "eu-west"],
        )
        step = ManifestStep(
            sql="up.sql",
            node_roles=["DATA"],
            clusters=["us-east"],
        )
        assert resolve_step_clusters(step, manifest) == ["us-east"]

    def test_falls_back_to_manifest_clusters(self) -> None:
        from posthog.clickhouse.migrations.runner import resolve_step_clusters

        manifest = MigrationManifest(
            description="test",
            steps=[],
            rollback=[],
            clusters=["us-east", "eu-west"],
        )
        step = ManifestStep(
            sql="up.sql",
            node_roles=["DATA"],
        )
        assert resolve_step_clusters(step, manifest) == ["us-east", "eu-west"]

    def test_falls_back_to_manifest_cluster_singular(self) -> None:
        from posthog.clickhouse.migrations.runner import resolve_step_clusters

        manifest = MigrationManifest(
            description="test",
            steps=[],
            rollback=[],
            cluster="posthog",
        )
        step = ManifestStep(
            sql="up.sql",
            node_roles=["DATA"],
        )
        assert resolve_step_clusters(step, manifest) == ["posthog"]

    def test_returns_none_when_no_clusters(self) -> None:
        from posthog.clickhouse.migrations.runner import resolve_step_clusters

        manifest = MigrationManifest(
            description="test",
            steps=[],
            rollback=[],
        )
        step = ManifestStep(
            sql="up.sql",
            node_roles=["DATA"],
        )
        assert resolve_step_clusters(step, manifest) is None


# ---------------------------------------------------------------------------
# check_cross_cluster_ordering
# ---------------------------------------------------------------------------


class TestCheckCrossClusterOrdering:
    @patch("posthog.clickhouse.migrations.runner.get_applied_migrations")
    def test_check_cross_cluster_ordering_passes(self, mock_applied: MagicMock) -> None:
        from posthog.clickhouse.migrations.runner import check_cross_cluster_ordering

        # Migration 5 completed on both clusters
        mock_applied.return_value = [
            {"migration_number": 5, "migration_name": "0005_foo"},
            {"migration_number": 5, "migration_name": "0005_foo"},
        ]

        clients = {
            "us-east": MagicMock(),
            "eu-west": MagicMock(),
        }

        result = check_cross_cluster_ordering(
            cluster_clients=clients,
            migration_number=6,
            database="posthog",
        )
        assert result is True

    @patch("posthog.clickhouse.migrations.runner.get_applied_migrations")
    def test_check_cross_cluster_ordering_blocks(self, mock_applied: MagicMock) -> None:
        from posthog.clickhouse.migrations.runner import check_cross_cluster_ordering

        # First cluster has migration 5, second does not
        mock_applied.side_effect = [
            [{"migration_number": 5, "migration_name": "0005_foo"}],
            [],  # eu-west has not applied migration 5
        ]

        clients = {
            "us-east": MagicMock(),
            "eu-west": MagicMock(),
        }

        result = check_cross_cluster_ordering(
            cluster_clients=clients,
            migration_number=6,
            database="posthog",
        )
        assert result is False

    @patch("posthog.clickhouse.migrations.runner.get_applied_migrations")
    def test_check_cross_cluster_ordering_first_migration(self, mock_applied: MagicMock) -> None:
        from posthog.clickhouse.migrations.runner import check_cross_cluster_ordering

        mock_applied.return_value = []

        clients = {
            "us-east": MagicMock(),
            "eu-west": MagicMock(),
        }

        # Migration 1 has no predecessor — should always pass
        result = check_cross_cluster_ordering(
            cluster_clients=clients,
            migration_number=1,
            database="posthog",
        )
        assert result is True

    @patch("posthog.clickhouse.migrations.runner.get_applied_migrations")
    def test_check_cross_cluster_ordering_single_cluster(self, mock_applied: MagicMock) -> None:
        from posthog.clickhouse.migrations.runner import check_cross_cluster_ordering

        mock_applied.return_value = [
            {"migration_number": 5, "migration_name": "0005_foo"},
        ]

        clients = {
            "us-east": MagicMock(),
        }

        result = check_cross_cluster_ordering(
            cluster_clients=clients,
            migration_number=6,
            database="posthog",
        )
        assert result is True


# ---------------------------------------------------------------------------
# Runner respects step clusters
# ---------------------------------------------------------------------------


class TestRunnerRespectsStepClusters:
    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_runner_respects_step_clusters_skips_unmatched(
        self, mock_execute: MagicMock, mock_record: MagicMock
    ) -> None:
        from posthog.clickhouse.migrations.runner import run_migration_up

        step1 = ManifestStep(
            sql="up.sql#step1",
            node_roles=["DATA"],
            clusters=["us-east"],
        )
        step2 = ManifestStep(
            sql="up.sql#step2",
            node_roles=["DATA"],
            clusters=["eu-west"],
        )

        migration = MagicMock()
        migration.get_steps.return_value = [
            (step1, "CREATE TABLE t1 (id UInt64) ENGINE = MergeTree() ORDER BY id"),
            (step2, "CREATE TABLE t2 (id UInt64) ENGINE = MergeTree() ORDER BY id"),
        ]
        migration.manifest = MigrationManifest(
            description="test",
            steps=[step1, step2],
            rollback=[],
        )

        mock_execute.return_value = {"host1": None}

        # current_cluster="us-east" should skip step2 (eu-west only)
        result = run_migration_up(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_test",
            current_cluster="us-east",
        )

        assert result is True
        # Only step1 should have been executed
        assert mock_execute.call_count == 1

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_runner_executes_all_steps_when_no_cluster_filter(
        self, mock_execute: MagicMock, mock_record: MagicMock
    ) -> None:
        from posthog.clickhouse.migrations.runner import run_migration_up

        step1 = ManifestStep(
            sql="up.sql#step1",
            node_roles=["DATA"],
            clusters=["us-east"],
        )
        step2 = ManifestStep(
            sql="up.sql#step2",
            node_roles=["DATA"],
        )

        migration = MagicMock()
        migration.get_steps.return_value = [
            (step1, "SELECT 1"),
            (step2, "SELECT 2"),
        ]
        migration.manifest = MigrationManifest(
            description="test",
            steps=[step1, step2],
            rollback=[],
        )

        mock_execute.return_value = {"host1": None}

        # No current_cluster means execute everything
        result = run_migration_up(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_test",
        )

        assert result is True
        assert mock_execute.call_count == 2

    @patch("posthog.clickhouse.migrations.runner._record_for_tracking")
    @patch("posthog.clickhouse.migrations.runner.execute_migration_step")
    def test_runner_uses_manifest_clusters_fallback(self, mock_execute: MagicMock, mock_record: MagicMock) -> None:
        from posthog.clickhouse.migrations.runner import run_migration_up

        step1 = ManifestStep(
            sql="up.sql",
            node_roles=["DATA"],
            # No per-step clusters — should use manifest-level
        )

        migration = MagicMock()
        migration.get_steps.return_value = [
            (step1, "SELECT 1"),
        ]
        migration.manifest = MigrationManifest(
            description="test",
            steps=[step1],
            rollback=[],
            clusters=["eu-west"],
        )

        mock_execute.return_value = {"host1": None}

        # current_cluster="us-east" but manifest says eu-west only
        result = run_migration_up(
            cluster=MagicMock(),
            migration=migration,
            database="test_db",
            migration_number=1,
            migration_name="0001_test",
            current_cluster="us-east",
        )

        assert result is True
        # Step should be skipped because us-east not in [eu-west]
        assert mock_execute.call_count == 0
