"""Unit tests for the legacy-to-declarative proof system.

These tests validate the core proof components (normalizer, classifier,
generator, comparator) without requiring Django or a live ClickHouse instance.
"""

from __future__ import annotations

import textwrap

from posthog.clickhouse.migration_tools.legacy_proof.normalizer import normalize_node_roles, normalize_sql


class TestNormalizeSQL:
    def test_collapses_whitespace(self):
        sql = "CREATE   TABLE\n  foo\n(\n  id  UInt64\n)"
        result = normalize_sql(sql)
        assert "  " not in result  # no double spaces

    def test_removes_comments(self):
        sql = "SELECT 1 -- this is a comment\nFROM foo"
        result = normalize_sql(sql)
        assert "comment" not in result

    def test_removes_block_comments(self):
        sql = "SELECT /* block */ 1 FROM foo"
        result = normalize_sql(sql)
        assert "block" not in result

    def test_strips_trailing_semicolons(self):
        sql = "SELECT 1;"
        result = normalize_sql(sql)
        assert not result.endswith(";")

    def test_normalizes_keywords_to_uppercase(self):
        sql = "create table foo (id uint64)"
        result = normalize_sql(sql)
        assert "CREATE" in result
        assert "TABLE" in result

    def test_preserves_jinja_templates(self):
        sql = "CREATE TABLE {{ database }}.foo ON CLUSTER '{{ cluster }}'"
        result = normalize_sql(sql)
        assert "{{ database }}" in result
        assert "{{ cluster }}" in result

    def test_empty_string(self):
        assert normalize_sql("") == ""

    def test_preserves_table_names(self):
        sql = "CREATE TABLE posthog.events (id UInt64)"
        result = normalize_sql(sql)
        # Table names should NOT be uppercased (only keywords)
        assert "posthog" in result
        assert "events" in result


class TestNormalizeNodeRoles:
    def test_data_role(self):
        assert normalize_node_roles(["data"]) == frozenset({"DATA"})

    def test_all_role(self):
        assert normalize_node_roles(["all"]) == frozenset({"ALL"})

    def test_multiple_roles(self):
        result = normalize_node_roles(["data", "coordinator"])
        assert result == frozenset({"DATA", "COORDINATOR"})

    def test_manifest_form_accepted(self):
        result = normalize_node_roles(["INGESTION_EVENTS"])
        assert result == frozenset({"INGESTION_EVENTS"})

    def test_enum_value_form(self):
        result = normalize_node_roles(["events"])
        assert result == frozenset({"INGESTION_EVENTS"})

    def test_empty(self):
        assert normalize_node_roles([]) == frozenset()

    def test_unknown_role_preserved(self):
        result = normalize_node_roles(["custom_role"])
        assert result == frozenset({"CUSTOM_ROLE"})


class TestClassifySource:
    """Test AST-based classification without Django."""

    def _classify(self, source: str):
        """Call the standalone classifier."""
        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import _classify_source

        return _classify_source(source)

    def test_exact_simple(self):
        source = textwrap.dedent("""
            from posthog.clickhouse.migration_tools.new_style import run_sql_with_exceptions
            operations = [
                run_sql_with_exceptions("CREATE TABLE foo (id UInt64)")
            ]
        """)
        classification, warnings = self._classify(source)
        assert classification == "exact"

    def test_empty_operations_exact(self):
        source = "operations = []"
        classification, warnings = self._classify(source)
        assert classification == "exact"
        assert any("no-op" in w.lower() or "empty" in w.lower() for w in warnings)

    def test_loop_with_run_sql_is_inferred(self):
        source = textwrap.dedent("""
            operations = []
            for col in ['a', 'b']:
                operations.append(run_sql_with_exceptions(f"ALTER TABLE ADD COLUMN {col}"))
        """)
        classification, warnings = self._classify(source)
        # Loops with run_sql_with_exceptions are deterministic → inferred
        assert classification == "inferred"

    def test_loop_without_run_sql_is_manual_review(self):
        source = textwrap.dedent("""
            operations = []
            for col in ['a', 'b']:
                operations.append(some_other_function(col))
        """)
        classification, warnings = self._classify(source)
        assert classification == "manual-review"

    def test_conditional_is_manual_review(self):
        source = textwrap.dedent("""
            operations = [op1] if DEPLOYMENT == 'cloud' else [op2]
        """)
        classification, warnings = self._classify(source)
        assert classification == "manual-review"

    def test_imported_sql_is_inferred(self):
        source = textwrap.dedent("""
            from posthog.clickhouse.table_engines.sql import CREATE_TABLE_SQL
            operations = [
                run_sql_with_exceptions(CREATE_TABLE_SQL)
            ]
        """)
        classification, warnings = self._classify(source)
        assert classification == "inferred"

    def test_no_operations_is_manual_review(self):
        source = "# empty migration\npass"
        classification, warnings = self._classify(source)
        assert classification == "manual-review"

    def test_syntax_error_is_manual_review(self):
        source = "def broken(:\n  pass"
        classification, warnings = self._classify(source)
        assert classification == "manual-review"
        assert any("SyntaxError" in w for w in warnings)


class TestGenerateManifestYAML:
    """Test manifest generation from standalone results."""

    def test_noop_migration(self):
        import yaml

        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import (
            StandaloneResult,
            generate_manifest_yaml,
        )

        result = StandaloneResult(
            migration_number=1,
            migration_name="0001_test",
            file_path="test.py",
            classification="exact",
            operations=[],
        )
        manifest_text = generate_manifest_yaml(result)
        manifest = yaml.safe_load(manifest_text)
        assert len(manifest["steps"]) == 1
        assert "no-op" in manifest["description"]

    def test_single_step(self):
        import yaml

        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import (
            StandaloneOp,
            StandaloneResult,
            generate_manifest_yaml,
        )

        result = StandaloneResult(
            migration_number=1,
            migration_name="0001_test",
            file_path="test.py",
            classification="exact",
            operations=[
                StandaloneOp(
                    index=0,
                    sql="CREATE TABLE foo (id UInt64)",
                    node_roles=["data"],
                    sharded=False,
                    is_alter_on_replicated_table=False,
                )
            ],
        )
        manifest_text = generate_manifest_yaml(result)
        manifest = yaml.safe_load(manifest_text)
        assert len(manifest["steps"]) == 1
        assert manifest["steps"][0]["sql"] == "up.sql"
        assert "DATA" in manifest["steps"][0]["node_roles"]

    def test_multi_step_uses_sections(self):
        import yaml

        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import (
            StandaloneOp,
            StandaloneResult,
            generate_manifest_yaml,
        )

        result = StandaloneResult(
            migration_number=2,
            migration_name="0002_test",
            file_path="test.py",
            classification="exact",
            operations=[
                StandaloneOp(0, "CREATE TABLE a", ["data"], False, False),
                StandaloneOp(1, "CREATE TABLE b", ["coordinator"], False, False),
            ],
        )
        manifest_text = generate_manifest_yaml(result)
        manifest = yaml.safe_load(manifest_text)
        assert len(manifest["steps"]) == 2
        assert "step_0" in manifest["steps"][0]["sql"]
        assert "step_1" in manifest["steps"][1]["sql"]

    def test_sharded_flag_preserved(self):
        import yaml

        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import (
            StandaloneOp,
            StandaloneResult,
            generate_manifest_yaml,
        )

        result = StandaloneResult(
            migration_number=3,
            migration_name="0003_test",
            file_path="test.py",
            classification="exact",
            operations=[
                StandaloneOp(0, "CREATE TABLE s", ["data"], True, False),
            ],
        )
        manifest_text = generate_manifest_yaml(result)
        manifest = yaml.safe_load(manifest_text)
        assert manifest["steps"][0].get("sharded") is True


class TestTemplatizeSQL:
    def test_replaces_database_prefix(self):
        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import _templatize_sql

        result = _templatize_sql("CREATE TABLE posthog.events", "posthog", "posthog", "")
        assert "{{ database }}" in result
        assert "posthog.events" not in result

    def test_replaces_cluster_in_quotes(self):
        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import _templatize_sql

        # Use different values for database and cluster to avoid replacement collision
        result = _templatize_sql("ON CLUSTER 'my_cluster'", "posthog", "my_cluster", "")
        assert "'{{ cluster }}'" in result

    def test_same_db_and_cluster_value(self):
        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import _templatize_sql

        # When database and cluster are both 'posthog', database replacement wins
        # because it runs first. This is expected behavior.
        result = _templatize_sql("ON CLUSTER 'posthog'", "posthog", "posthog", "")
        assert "'{{ database }}'" in result

    def test_no_replacement_when_empty(self):
        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import _templatize_sql

        result = _templatize_sql("SELECT 1", "", "", "")
        assert result == "SELECT 1"


class TestCheckpointEras:
    """Test checkpoint era definitions cover the full range."""

    def test_eras_cover_full_range(self):
        from posthog.clickhouse.migration_tools.legacy_proof.checkpoint_runner import CHECKPOINT_ERAS

        # Eras should cover 1-223
        all_covered = set()
        for cp in CHECKPOINT_ERAS:
            for i in range(cp.era_range[0], cp.era_range[1] + 1):
                all_covered.add(i)

        # At minimum, first and last legacy migrations should be covered
        assert 1 in all_covered
        assert 223 in all_covered

    def test_eras_are_ordered(self):
        from posthog.clickhouse.migration_tools.legacy_proof.checkpoint_runner import CHECKPOINT_ERAS

        for i in range(len(CHECKPOINT_ERAS) - 1):
            assert CHECKPOINT_ERAS[i].era_range[0] < CHECKPOINT_ERAS[i + 1].era_range[0]
