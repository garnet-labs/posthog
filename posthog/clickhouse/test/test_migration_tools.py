from __future__ import annotations

import hashlib
import tempfile
import textwrap
from pathlib import Path

import unittest
from unittest.mock import MagicMock

import posthog.clickhouse.test._stubs  # noqa: F401


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


class TestRenderSql(unittest.TestCase):
    def test_render_sql_basic(self) -> None:
        from posthog.clickhouse.migration_tools.jinja_env import render_sql

        result = render_sql("CREATE TABLE {{ database }}.foo", {"database": "posthog"})
        self.assertEqual(result, "CREATE TABLE posthog.foo")


class TestValidatorRules(unittest.TestCase):
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


class TestDiscoverMigrations(unittest.TestCase):
    def test_discover_migrations(self) -> None:
        from posthog.clickhouse.migration_tools.runner import discover_migrations

        d = Path(tempfile.mkdtemp())

        (d / "0001_initial.py").write_text("# migration")

        mig_dir = d / "0002_add_column"
        mig_dir.mkdir()
        (mig_dir / "manifest.yaml").write_text("description: test\nsteps: []\nrollback: []")

        (d / "__init__.py").write_text("")
        (d / "README.md").write_text("docs")

        migrations = discover_migrations(d)
        self.assertEqual(len(migrations), 2)
        self.assertEqual(migrations[0]["number"], 1)
        self.assertEqual(migrations[0]["style"], "py")
        self.assertEqual(migrations[1]["number"], 2)
        self.assertEqual(migrations[1]["style"], "new")


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


class TestGetPendingMigrations(unittest.TestCase):
    def test_get_pending_migrations_excludes_applied(self) -> None:
        from posthog.clickhouse.migration_tools.runner import get_pending_migrations

        d = Path(tempfile.mkdtemp())
        (d / "0001_initial.py").write_text("# migration")
        (d / "0002_add_col.py").write_text("# migration")

        mock_client = MagicMock()
        mock_client.execute.return_value = [
            (1, "0001_initial", -1, "*", "*", "up", "complete", "2024-01-01", True),
        ]

        pending = get_pending_migrations(mock_client, "default", migrations_dir=d)
        numbers = [m["number"] for m in pending]
        self.assertNotIn(1, numbers)
        self.assertIn(2, numbers)


class TestGetAppliedMigrations(unittest.TestCase):
    def test_get_applied_migrations_avoids_alias_reuse(self) -> None:
        from posthog.clickhouse.migration_tools.tracking import get_applied_migrations

        mock_client = MagicMock()
        mock_client.execute.return_value = [(224, "0224_ch_migrate_bootstrap", "up", "2024-01-01 00:00:00")]

        applied = get_applied_migrations(mock_client, "default")

        sql = mock_client.execute.call_args.args[0]
        self.assertIn("argMax(direction, applied_at) AS latest_direction", sql)
        self.assertIn("max(applied_at) AS latest_applied_at", sql)
        self.assertNotIn("max(applied_at) AS applied_at", sql)
        self.assertEqual(applied[0]["migration_number"], 224)


class TestAdvisoryLock(unittest.TestCase):
    def test_advisory_lock_prevents_concurrent_apply(self) -> None:
        from datetime import UTC, datetime, timedelta

        from posthog.clickhouse.migration_tools.tracking import acquire_apply_lock

        mock_client = MagicMock()
        lock_time = datetime.now(tz=UTC) - timedelta(minutes=5)
        mock_client.execute.return_value = [("other-host", lock_time)]

        acquired, reason = acquire_apply_lock(mock_client, "default", "my-host")

        self.assertFalse(acquired)
        self.assertIn("other-host", reason)

    def test_advisory_lock_expired_allows_apply(self) -> None:
        from posthog.clickhouse.migration_tools.tracking import acquire_apply_lock

        mock_client = MagicMock()
        mock_client.execute.return_value = []

        acquired, reason = acquire_apply_lock(mock_client, "default", "my-host")

        self.assertTrue(acquired)
        self.assertEqual(reason, "")

    def test_release_apply_lock_inserts_shadow_row(self) -> None:
        from posthog.clickhouse.migration_tools.tracking import release_apply_lock

        mock_client = MagicMock()
        release_apply_lock(mock_client, "default", "my-host")

        mock_client.execute.assert_called_once()
        call_args = mock_client.execute.call_args
        params = call_args[0][1][0]
        self.assertFalse(params[-1])


class TestEcosystemCompleteness(unittest.TestCase):
    def test_warns_on_missing_companion(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import MigrationManifest
        from posthog.clickhouse.migration_tools.validator import check_ecosystem_completeness

        manifest = MigrationManifest(description="test", steps=[], rollback=[])
        sql = "ALTER TABLE sharded_events ADD COLUMN foo String;"
        results = check_ecosystem_completeness(manifest, sql)
        self.assertTrue(any(r.rule == "ecosystem_completeness" for r in results))
        self.assertTrue(any("writable_events" in r.message for r in results))

    def test_passes_when_complete(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import MigrationManifest
        from posthog.clickhouse.migration_tools.validator import check_ecosystem_completeness

        manifest = MigrationManifest(description="test", steps=[], rollback=[])
        sql = textwrap.dedent("""\
            ALTER TABLE sharded_events ADD COLUMN foo String;
            ALTER TABLE writable_events ADD COLUMN foo String;
            ALTER TABLE events ADD COLUMN foo String;
            ALTER TABLE kafka_events_json ADD COLUMN foo String;
            ALTER MATERIALIZED VIEW events_json_mv ADD COLUMN foo String;
        """)
        results = check_ecosystem_completeness(manifest, sql)
        ecosystem_results = [r for r in results if r.rule == "ecosystem_completeness"]
        self.assertEqual(len(ecosystem_results), 0)

    def test_manifest_ecosystem_field(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import MigrationManifest
        from posthog.clickhouse.migration_tools.validator import check_ecosystem_completeness

        manifest = MigrationManifest(description="test", steps=[], rollback=[], ecosystem="events")
        sql = "ALTER TABLE sharded_events ADD COLUMN foo String;"
        results = check_ecosystem_completeness(manifest, sql)
        self.assertTrue(any(r.rule == "ecosystem_completeness" for r in results))

    def test_unknown_ecosystem_name_warns(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import MigrationManifest
        from posthog.clickhouse.migration_tools.validator import check_ecosystem_completeness

        manifest = MigrationManifest(description="test", steps=[], rollback=[], ecosystem="nonexistent")
        sql = "SELECT 1;"
        results = check_ecosystem_completeness(manifest, sql)
        self.assertTrue(any("no such ecosystem" in r.message for r in results))


class TestCreationOrder(unittest.TestCase):
    def test_rejects_mv_before_kafka(self) -> None:
        from posthog.clickhouse.migration_tools.validator import check_creation_order

        sql = textwrap.dedent("""\
            CREATE MATERIALIZED VIEW IF NOT EXISTS my_mv
            TO posthog.writable_events
            AS SELECT * FROM posthog.kafka_events_json;

            CREATE TABLE IF NOT EXISTS kafka_events_json (id UInt64) ENGINE = Kafka();
        """)
        results = check_creation_order(sql)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].rule, "creation_order")
        self.assertEqual(results[0].severity, "error")

    def test_passes_correct_order(self) -> None:
        from posthog.clickhouse.migration_tools.validator import check_creation_order

        sql = textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS kafka_events_json (id UInt64) ENGINE = Kafka();
            CREATE TABLE IF NOT EXISTS sharded_events (id UInt64) ENGINE = ReplicatedMergeTree();
            CREATE TABLE IF NOT EXISTS writable_events (id UInt64) ENGINE = Distributed();
            CREATE MATERIALIZED VIEW IF NOT EXISTS events_json_mv
            TO posthog.writable_events
            AS SELECT * FROM posthog.kafka_events_json;
        """)
        results = check_creation_order(sql)
        self.assertEqual(len(results), 0)

    def test_rejects_distributed_before_mergetree(self) -> None:
        from posthog.clickhouse.migration_tools.validator import check_creation_order

        sql = textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS writable_events (id UInt64) ENGINE = Distributed();
            CREATE TABLE IF NOT EXISTS sharded_events (id UInt64) ENGINE = MergeTree();
        """)
        results = check_creation_order(sql)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].severity, "error")


class TestCrossClusterTargeting(unittest.TestCase):
    def test_warns_distributed_on_wrong_role(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import ManifestStep, MigrationManifest
        from posthog.clickhouse.migration_tools.validator import check_cross_cluster_targeting

        manifest = MigrationManifest(
            description="test",
            steps=[
                ManifestStep(
                    sql="up.sql#create_distributed",
                    node_roles=["DATA"],
                    comment="Create distributed table",
                ),
            ],
            rollback=[],
        )
        results = check_cross_cluster_targeting(manifest)
        self.assertTrue(any(r.rule == "cross_cluster_targeting" for r in results))
        self.assertTrue(any("COORDINATOR" in r.message for r in results))

    def test_passes_distributed_on_coordinator(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import ManifestStep, MigrationManifest
        from posthog.clickhouse.migration_tools.validator import check_cross_cluster_targeting

        manifest = MigrationManifest(
            description="test",
            steps=[
                ManifestStep(
                    sql="up.sql#create_distributed",
                    node_roles=["COORDINATOR"],
                    comment="Create distributed table",
                ),
            ],
            rollback=[],
        )
        results = check_cross_cluster_targeting(manifest)
        self.assertEqual(len(results), 0)


class TestIngestionPipelineTemplate(unittest.TestCase):
    def _config(self) -> dict:
        return {
            "table": "sessions_v4",
            "columns": [
                {"name": "session_id", "type": "UUID"},
                {"name": "team_id", "type": "Int64"},
                {"name": "timestamp", "type": "DateTime64(6, 'UTC')"},
            ],
            "order_by": ["team_id", "toStartOfHour(timestamp)", "session_id"],
            "partition_by": "toYYYYMM(timestamp)",
            "kafka_topic": "session_recordings",
            "kafka_group": "sessions_v4_consumer",
        }

    def test_generates_all_objects(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_steps

        steps = generate_steps("ingestion_pipeline", self._config())
        self.assertEqual(len(steps), 5)

        sqls = [sql for _, sql in steps]
        self.assertTrue(any("kafka_sessions_v4" in sql for sql in sqls))
        self.assertTrue(any("sharded_sessions_v4" in sql for sql in sqls))
        self.assertTrue(any("writable_sessions_v4" in sql for sql in sqls))
        self.assertTrue(any("sessions_v4_mv" in sql for sql in sqls))

    def test_correct_node_roles(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_steps

        steps = generate_steps("ingestion_pipeline", self._config())

        kafka_step = steps[0][0]
        sharded_step = steps[1][0]
        writable_step = steps[2][0]
        readable_step = steps[3][0]
        mv_step = steps[4][0]

        self.assertIn("INGESTION_EVENTS", kafka_step.node_roles)
        self.assertIn("DATA", sharded_step.node_roles)
        self.assertTrue(sharded_step.sharded)
        self.assertIn("COORDINATOR", writable_step.node_roles)
        self.assertIn("ALL", readable_step.node_roles)
        self.assertIn("INGESTION_EVENTS", mv_step.node_roles)

    def test_correct_order(self) -> None:
        """Kafka(tier 0) before MergeTree(tier 1) before Distributed(tier 2) before MV(tier 3)."""
        from posthog.clickhouse.migration_tools.templates import generate_steps

        steps = generate_steps("ingestion_pipeline", self._config())
        sqls = [sql for _, sql in steps]

        # Kafka first, MV last
        self.assertIn("Kafka()", sqls[0])
        self.assertIn("MATERIALIZED VIEW", sqls[4])
        # Sharded (MergeTree) before Distributed
        self.assertIn("ReplicatedMergeTree()", sqls[1])
        self.assertIn("Distributed(", sqls[2])

    def test_rollback_reverse_order(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_rollback_steps

        steps = generate_rollback_steps("ingestion_pipeline", self._config())
        self.assertEqual(len(steps), 5)

        # MV dropped first, Kafka dropped last
        self.assertIn("sessions_v4_mv", steps[0][1])
        self.assertIn("kafka_sessions_v4", steps[4][1])

    def test_no_on_cluster_in_sql(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_steps

        steps = generate_steps("ingestion_pipeline", self._config())
        for _, sql in steps:
            self.assertNotIn("ON CLUSTER", sql.upper())


class TestAddColumnTemplate(unittest.TestCase):
    def _config(self) -> dict:
        return {
            "ecosystem": "events",
            "column": {"name": "foo_bar", "type": "String", "default": "''"},
        }

    def test_generates_alter_steps(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_steps

        steps = generate_steps("add_column", self._config())

        # Should include: drop MV, alter sharded, alter writable, alter readable, alter kafka, recreate MV
        self.assertGreaterEqual(len(steps), 5)

        # Check sharded alter exists with correct flags
        sharded_alters = [(s, sql) for s, sql in steps if s.sharded and s.is_alter_on_replicated_table]
        self.assertEqual(len(sharded_alters), 1)
        self.assertIn("foo_bar", sharded_alters[0][1])
        self.assertIn("sharded_events", sharded_alters[0][1])

    def test_rollback_reverses(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_rollback_steps

        steps = generate_rollback_steps("add_column", self._config())
        self.assertGreaterEqual(len(steps), 5)

        # Rollback should DROP COLUMN
        drop_col_steps = [sql for _, sql in steps if "DROP COLUMN" in sql]
        self.assertGreater(len(drop_col_steps), 0)

        # Every DROP COLUMN should reference foo_bar
        for sql in drop_col_steps:
            self.assertIn("foo_bar", sql)

    def test_unknown_ecosystem_raises(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_steps

        with self.assertRaises(ValueError) as ctx:
            generate_steps("add_column", {"ecosystem": "nonexistent", "column": {"name": "x", "type": "String"}})
        self.assertIn("nonexistent", str(ctx.exception))


class TestCrossClusterReadableTemplate(unittest.TestCase):
    def test_generates_distributed_and_dict(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_steps

        config = {
            "source_table": "channel_definition",
            "source_cluster": "main",
            "target_cluster": "sessions",
            "create_dictionary": True,
            "dict_layout": "flat",
        }
        steps = generate_steps("cross_cluster_readable", config)
        self.assertEqual(len(steps), 2)

        # Distributed table
        dist_step, dist_sql = steps[0]
        self.assertIn("Distributed('main'", dist_sql)
        self.assertEqual(dist_step.clusters, ["sessions"])

        # Dictionary
        dict_step, dict_sql = steps[1]
        self.assertIn("DICTIONARY", dict_sql)
        self.assertIn("channel_definition_dict", dict_sql)
        self.assertEqual(dict_step.clusters, ["sessions"])

    def test_without_dictionary(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_steps

        config = {
            "source_table": "channel_definition",
            "source_cluster": "main",
            "target_cluster": "sessions",
        }
        steps = generate_steps("cross_cluster_readable", config)
        self.assertEqual(len(steps), 1)


class TestTemplateManifestParsing(unittest.TestCase):
    def _write_manifest(self, content: str) -> Path:
        d = tempfile.mkdtemp()
        p = Path(d) / "manifest.yaml"
        p.write_text(textwrap.dedent(content))
        return p

    def test_backward_compatible(self) -> None:
        """Manifests with 'steps' still work as before."""
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
        self.assertIsNone(manifest.template)
        self.assertEqual(len(manifest.steps), 1)

    def test_template_manifest_parses(self) -> None:
        """Manifests with 'template' parse correctly."""
        from posthog.clickhouse.migration_tools.manifest import parse_manifest

        p = self._write_manifest("""\
            description: "Add sessions v4 ingestion pipeline"
            template: ingestion_pipeline
            config:
              table: sessions_v4
              columns:
                - name: session_id
                  type: UUID
                - name: team_id
                  type: Int64
              order_by: [team_id, session_id]
              kafka_topic: session_recordings
        """)
        manifest = parse_manifest(p)
        self.assertEqual(manifest.template, "ingestion_pipeline")
        assert manifest.template_config is not None
        self.assertEqual(manifest.template_config["table"], "sessions_v4")
        self.assertEqual(len(manifest.steps), 0)  # Steps are generated at runtime

    def test_template_manifest_requires_config(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import parse_manifest

        p = self._write_manifest("""\
            description: "Missing config"
            template: ingestion_pipeline
        """)
        with self.assertRaises(ValueError) as ctx:
            parse_manifest(p)
        self.assertIn("config", str(ctx.exception))

    def test_manifest_without_steps_or_template_fails(self) -> None:
        from posthog.clickhouse.migration_tools.manifest import parse_manifest

        p = self._write_manifest("""\
            description: "Neither steps nor template"
        """)
        with self.assertRaises(ValueError) as ctx:
            parse_manifest(p)
        self.assertIn("steps", str(ctx.exception))


class TestShardedTableTemplate(unittest.TestCase):
    def test_generates_three_objects(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_steps

        config = {
            "table": "my_table",
            "columns": [
                {"name": "id", "type": "UUID"},
                {"name": "team_id", "type": "Int64"},
            ],
            "order_by": ["team_id", "id"],
        }
        steps = generate_steps("sharded_table", config)
        self.assertEqual(len(steps), 3)

        # Sharded, writable, readable
        self.assertTrue(steps[0][0].sharded)
        self.assertIn("DATA", steps[0][0].node_roles)
        self.assertIn("COORDINATOR", steps[1][0].node_roles)
        self.assertIn("ALL", steps[2][0].node_roles)

    def test_rollback_reverse_order(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_rollback_steps

        config = {
            "table": "my_table",
            "columns": [{"name": "id", "type": "UUID"}],
            "order_by": ["id"],
        }
        steps = generate_rollback_steps("sharded_table", config)
        self.assertEqual(len(steps), 3)

        # Readable dropped first, sharded last
        self.assertIn("my_table", steps[0][1])
        self.assertIn("sharded_my_table", steps[2][1])


class TestUnknownTemplate(unittest.TestCase):
    def test_unknown_template_raises(self) -> None:
        from posthog.clickhouse.migration_tools.templates import generate_steps

        with self.assertRaises(ValueError) as ctx:
            generate_steps("nonexistent_template", {})
        self.assertIn("nonexistent_template", str(ctx.exception))


class TestDumpSchema(unittest.TestCase):
    def test_dump_schema_parses_system_tables(self) -> None:
        from posthog.clickhouse.migration_tools.schema_introspect import dump_schema

        mock_client = MagicMock()
        mock_client.execute.side_effect = [
            # system.tables result
            [
                (
                    "events",
                    "MergeTree",
                    "MergeTree() ORDER BY (team_id, timestamp)",
                    "team_id, timestamp",
                    "toYYYYMM(timestamp)",
                    "team_id, timestamp",
                    "",
                ),
                ("events_dist", "Distributed", "Distributed('cluster', 'default', 'events')", "", "", "", ""),
            ],
            # system.columns result
            [
                ("events", "team_id", "Int64", "", "", 1),
                ("events", "timestamp", "DateTime64(6, 'UTC')", "", "", 2),
                ("events_dist", "team_id", "Int64", "", "", 1),
            ],
        ]

        schema = dump_schema(mock_client, "default")

        self.assertEqual(len(schema), 2)
        self.assertIn("events", schema)
        self.assertIn("events_dist", schema)
        self.assertEqual(schema["events"].engine, "MergeTree")
        self.assertEqual(schema["events"].sorting_key, "team_id, timestamp")
        self.assertEqual(len(schema["events"].columns), 2)
        self.assertEqual(schema["events"].columns[0].name, "team_id")
        self.assertEqual(schema["events"].columns[0].type, "Int64")
        self.assertEqual(len(schema["events_dist"].columns), 1)


class TestCompareSchemas(unittest.TestCase):
    def _make_table(self, name: str, engine: str = "MergeTree", columns: list | None = None, sorting_key: str = ""):
        from posthog.clickhouse.migration_tools.schema_introspect import TableSchema

        cols = columns if columns is not None else []
        return TableSchema(name=name, engine=engine, columns=cols, sorting_key=sorting_key)

    def _make_col(self, name: str, type: str):
        from posthog.clickhouse.migration_tools.schema_introspect import ColumnSchema

        return ColumnSchema(name=name, type=type)

    def test_compare_schemas_detects_missing_column(self) -> None:
        from posthog.clickhouse.migration_tools.schema_introspect import compare_schemas

        expected = {
            "events": self._make_table(
                "events", columns=[self._make_col("id", "UInt64"), self._make_col("name", "String")]
            ),
        }
        actual = {
            "events": self._make_table("events", columns=[self._make_col("id", "UInt64")]),
        }

        diffs = compare_schemas(expected, actual)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].diff_type, "missing_column")
        self.assertEqual(diffs[0].table, "events")
        self.assertEqual(diffs[0].column, "name")

    def test_compare_schemas_detects_type_mismatch(self) -> None:
        from posthog.clickhouse.migration_tools.schema_introspect import compare_schemas

        expected = {
            "events": self._make_table("events", columns=[self._make_col("id", "UInt64")]),
        }
        actual = {
            "events": self._make_table("events", columns=[self._make_col("id", "String")]),
        }

        diffs = compare_schemas(expected, actual)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].diff_type, "type_mismatch")
        self.assertEqual(diffs[0].column, "id")
        self.assertEqual(diffs[0].expected, "UInt64")
        self.assertEqual(diffs[0].actual, "String")


class TestDetectDrift(unittest.TestCase):
    def test_detect_drift_across_hosts(self) -> None:
        from posthog.clickhouse.cluster import ConnectionInfo, HostInfo
        from posthog.clickhouse.migration_tools.schema_introspect import ColumnSchema, TableSchema, detect_drift

        host1 = HostInfo(
            ConnectionInfo("host1", 9000),
            shard_num=1,
            replica_num=1,
            host_cluster_type="default",
            host_cluster_role="DATA",
        )
        host2 = HostInfo(
            ConnectionInfo("host2", 9000),
            shard_num=1,
            replica_num=2,
            host_cluster_type="default",
            host_cluster_role="DATA",
        )

        schema_host1 = {
            "events": TableSchema(
                name="events",
                engine="MergeTree",
                columns=[ColumnSchema(name="id", type="UInt64"), ColumnSchema(name="name", type="String")],
            ),
        }
        schema_host2 = {
            "events": TableSchema(
                name="events",
                engine="MergeTree",
                columns=[ColumnSchema(name="id", type="UInt64")],  # missing 'name' column
            ),
        }

        mock_cluster = MagicMock()
        mock_futures = MagicMock()
        mock_futures.result.return_value = {host1: schema_host1, host2: schema_host2}
        mock_cluster.map_all_hosts.return_value = mock_futures

        diffs = detect_drift(mock_cluster, "default")

        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].diff_type, "missing_column")
        self.assertEqual(diffs[0].column, "name")
        self.assertIn("host2", diffs[0].host)


if __name__ == "__main__":
    unittest.main()
