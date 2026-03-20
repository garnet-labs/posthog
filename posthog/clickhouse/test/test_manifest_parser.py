import pytest

import yaml

from posthog.clickhouse.migrations.manifest import ManifestStep, MigrationManifest, parse_manifest


class TestParseValidManifest:
    def test_parse_valid_manifest(self, tmp_path):
        manifest_yaml = {
            "description": "Add sharded events table",
            "steps": [
                {
                    "sql": "up.sql#create_local",
                    "node_roles": ["DATA"],
                    "comment": "Create local table",
                    "sharded": True,
                },
                {
                    "sql": "up.sql#create_distributed",
                    "node_roles": ["COORDINATOR"],
                    "comment": "Create distributed table",
                },
            ],
            "rollback": [
                {
                    "sql": "down.sql",
                    "node_roles": ["DATA", "COORDINATOR"],
                },
            ],
        }
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(manifest_yaml))

        result = parse_manifest(manifest_file)

        assert isinstance(result, MigrationManifest)
        assert result.description == "Add sharded events table"
        assert len(result.steps) == 2
        assert len(result.rollback) == 1

        step0 = result.steps[0]
        assert isinstance(step0, ManifestStep)
        assert step0.sql == "up.sql#create_local"
        assert step0.node_roles == ["DATA"]
        assert step0.comment == "Create local table"
        assert step0.sharded is True

        step1 = result.steps[1]
        assert step1.sql == "up.sql#create_distributed"
        assert step1.node_roles == ["COORDINATOR"]
        assert step1.sharded is False

        rollback0 = result.rollback[0]
        assert rollback0.sql == "down.sql"
        assert rollback0.node_roles == ["DATA", "COORDINATOR"]

    def test_parse_minimal_manifest(self, tmp_path):
        manifest_yaml = {
            "description": "Simple migration",
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

        assert result.description == "Simple migration"
        assert len(result.steps) == 1
        assert len(result.rollback) == 0
        assert result.cluster is None
        assert result.clusters is None

    def test_parse_manifest_missing_description(self, tmp_path):
        manifest_yaml = {
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

        with pytest.raises(ValueError, match="description"):
            parse_manifest(manifest_file)

    def test_parse_manifest_missing_steps(self, tmp_path):
        manifest_yaml = {
            "description": "Missing steps",
            "rollback": [],
        }
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(manifest_yaml))

        with pytest.raises(ValueError, match="steps"):
            parse_manifest(manifest_file)

    def test_parse_manifest_invalid_node_role(self, tmp_path):
        manifest_yaml = {
            "description": "Bad role",
            "steps": [
                {
                    "sql": "up.sql",
                    "node_roles": ["INVALID_ROLE"],
                },
            ],
            "rollback": [],
        }
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(manifest_yaml))

        with pytest.raises(ValueError, match="node_role"):
            parse_manifest(manifest_file)

    def test_parse_manifest_with_clusters(self, tmp_path):
        manifest_yaml = {
            "description": "Per-step clusters",
            "steps": [
                {
                    "sql": "up.sql#step1",
                    "node_roles": ["DATA"],
                    "clusters": ["us-east", "eu-west"],
                },
                {
                    "sql": "up.sql#step2",
                    "node_roles": ["COORDINATOR"],
                },
            ],
            "rollback": [],
            "clusters": ["us-east", "eu-west"],
        }
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(manifest_yaml))

        result = parse_manifest(manifest_file)

        assert result.clusters == ["us-east", "eu-west"]
        assert result.steps[0].clusters == ["us-east", "eu-west"]
        assert result.steps[1].clusters is None

    def test_parse_manifest_with_async(self, tmp_path):
        manifest_yaml = {
            "description": "Async migration",
            "steps": [
                {
                    "sql": "up.sql",
                    "node_roles": ["DATA"],
                    "async": True,
                    "timeout": "30m",
                    "healthcheck": "SELECT 1",
                },
            ],
            "rollback": [],
        }
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(manifest_yaml))

        result = parse_manifest(manifest_file)

        step = result.steps[0]
        assert step.async_ is True
        assert step.timeout == "30m"
        assert step.healthcheck == "SELECT 1"

    def test_parse_manifest_with_is_alter_on_replicated_table(self, tmp_path):
        manifest_yaml = {
            "description": "Alter replicated",
            "steps": [
                {
                    "sql": "up.sql",
                    "node_roles": ["DATA"],
                    "is_alter_on_replicated_table": True,
                },
            ],
            "rollback": [],
        }
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(manifest_yaml))

        result = parse_manifest(manifest_file)

        assert result.steps[0].is_alter_on_replicated_table is True

    def test_parse_manifest_with_cluster(self, tmp_path):
        manifest_yaml = {
            "description": "With cluster",
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
