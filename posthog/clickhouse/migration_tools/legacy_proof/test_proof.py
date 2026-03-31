"""Tests for the legacy-to-declarative proof system.

These tests validate the extraction, generation, comparison, and
reporting pipeline WITHOUT requiring a live ClickHouse instance.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import (
    StandaloneOp,
    StandaloneResult,
    _classify_source,
    generate_down_sql,
    generate_manifest_yaml,
    generate_up_sql,
)
from posthog.clickhouse.migration_tools.legacy_proof.normalizer import (
    normalize_node_roles,
    normalize_sql,
)


# --- Classification tests ---


class TestClassifySource:
    def test_exact_simple_run_sql(self):
        source = textwrap.dedent("""\
            from posthog.clickhouse.client.migration_tools import run_sql_with_exceptions
            operations = [run_sql_with_exceptions("SELECT 1")]
        """)
        cls, warns = _classify_source(source)
        assert cls == "exact"

    def test_exact_empty_ops(self):
        source = 'operations = []'
        cls, warns = _classify_source(source)
        assert cls == "exact"
        assert any("no-op" in w.lower() or "empty" in w.lower() for w in warns)

    def test_exact_annotated_empty_ops(self):
        source = textwrap.dedent("""\
            from typing import Never
            operations: list[Never] = []
        """)
        cls, warns = _classify_source(source)
        assert cls == "exact"

    def test_inferred_sql_helper(self):
        source = textwrap.dedent("""\
            from posthog.clickhouse.client.migration_tools import run_sql_with_exceptions
            from posthog.models.event.sql import EVENTS_TABLE_SQL
            operations = [run_sql_with_exceptions(EVENTS_TABLE_SQL())]
        """)
        cls, warns = _classify_source(source)
        assert cls == "inferred"
        assert any("helper" in w.lower() for w in warns)

    def test_manual_review_run_python(self):
        source = textwrap.dedent("""\
            from infi.clickhouse_orm import migrations
            def do_something(db): pass
            operations = [migrations.RunPython(do_something)]
        """)
        cls, warns = _classify_source(source)
        assert cls == "manual-review"
        assert any("RunPython" in w for w in warns)

    def test_inferred_loop_with_run_sql(self):
        source = textwrap.dedent("""\
            from posthog.clickhouse.client.migration_tools import run_sql_with_exceptions
            operations = []
            for col in ["a", "b"]:
                operations.append(run_sql_with_exceptions(f"ALTER TABLE t ADD COLUMN {col} String"))
        """)
        cls, warns = _classify_source(source)
        assert cls == "inferred"
        assert any("loop" in w.lower() for w in warns)

    def test_manual_review_conditional(self):
        source = textwrap.dedent("""\
            from posthog.clickhouse.client.migration_tools import run_sql_with_exceptions
            operations = [run_sql_with_exceptions("SELECT 1")] if True else []
        """)
        cls, warns = _classify_source(source)
        assert cls == "manual-review"

    def test_manual_review_no_operations(self):
        source = "x = 1"
        cls, warns = _classify_source(source)
        assert cls == "manual-review"
        assert any("No 'operations'" in w for w in warns)


# --- SQL Normalization tests ---


class TestNormalizeSql:
    def test_whitespace_collapse(self):
        assert normalize_sql("SELECT   1   FROM  t") == normalize_sql("SELECT 1 FROM t")

    def test_comment_removal(self):
        sql = "SELECT 1 -- comment\nFROM t"
        normalized = normalize_sql(sql)
        assert "--" not in normalized

    def test_keyword_uppercase(self):
        assert "SELECT" in normalize_sql("select 1 from t")
        assert "FROM" in normalize_sql("select 1 from t")

    def test_trailing_semicolon(self):
        assert normalize_sql("SELECT 1;") == normalize_sql("SELECT 1")

    def test_preserves_jinja_templates(self):
        sql = "SELECT * FROM {{ database }}.events"
        normalized = normalize_sql(sql)
        assert "{{ database }}" in normalized


# --- Role normalization tests ---


class TestNormalizeNodeRoles:
    def test_canonical_mapping(self):
        assert normalize_node_roles(["data"]) == frozenset({"DATA"})
        assert normalize_node_roles(["events"]) == frozenset({"INGESTION_EVENTS"})
        assert normalize_node_roles(["all"]) == frozenset({"ALL"})

    def test_already_canonical(self):
        assert normalize_node_roles(["DATA"]) == frozenset({"DATA"})
        assert normalize_node_roles(["INGESTION_EVENTS"]) == frozenset({"INGESTION_EVENTS"})


# --- Manifest generation tests ---


class TestGenerateManifest:
    def test_single_step(self):
        result = StandaloneResult(
            migration_number=1,
            migration_name="0001_initial",
            file_path="test.py",
            classification="exact",
            operations=[
                StandaloneOp(index=0, sql="SELECT 1", node_roles=["data"], sharded=False, is_alter_on_replicated_table=False),
            ],
        )
        manifest = generate_manifest_yaml(result)
        assert "up.sql" in manifest
        assert "DATA" in manifest
        assert "step_0" not in manifest  # single step doesn't use sections

    def test_multi_step(self):
        result = StandaloneResult(
            migration_number=2,
            migration_name="0002_test",
            file_path="test.py",
            classification="inferred",
            operations=[
                StandaloneOp(index=0, sql="SELECT 1", node_roles=["data"], sharded=False, is_alter_on_replicated_table=False),
                StandaloneOp(index=1, sql="SELECT 2", node_roles=["coordinator"], sharded=False, is_alter_on_replicated_table=False),
            ],
        )
        manifest = generate_manifest_yaml(result)
        assert "step_0" in manifest
        assert "step_1" in manifest
        assert "DATA" in manifest
        assert "COORDINATOR" in manifest

    def test_sharded_alter_replicated(self):
        result = StandaloneResult(
            migration_number=3,
            migration_name="0003_test",
            file_path="test.py",
            classification="exact",
            operations=[
                StandaloneOp(index=0, sql="ALTER TABLE t", node_roles=["data"], sharded=True, is_alter_on_replicated_table=True),
            ],
        )
        manifest = generate_manifest_yaml(result)
        assert "sharded: true" in manifest
        assert "is_alter_on_replicated_table: true" in manifest

    def test_empty_ops(self):
        result = StandaloneResult(
            migration_number=4,
            migration_name="0004_noop",
            file_path="test.py",
            classification="exact",
            operations=[],
        )
        manifest = generate_manifest_yaml(result)
        assert "no-op" in manifest


# --- Up SQL generation tests ---


class TestGenerateUpSql:
    def test_single_step(self):
        result = StandaloneResult(
            migration_number=1,
            migration_name="0001_test",
            file_path="test.py",
            operations=[
                StandaloneOp(index=0, sql="CREATE TABLE posthog.events (id UInt64)", node_roles=["data"], sharded=False, is_alter_on_replicated_table=False),
            ],
        )
        up_sql = generate_up_sql(result, "posthog", "posthog", "")
        assert "{{ database }}" in up_sql
        assert "posthog.events" not in up_sql  # should be templatized

    def test_multi_step_sections(self):
        result = StandaloneResult(
            migration_number=2,
            migration_name="0002_test",
            file_path="test.py",
            operations=[
                StandaloneOp(index=0, sql="SELECT 1", node_roles=["data"], sharded=False, is_alter_on_replicated_table=False),
                StandaloneOp(index=1, sql="SELECT 2", node_roles=["data"], sharded=False, is_alter_on_replicated_table=False),
            ],
        )
        up_sql = generate_up_sql(result, "posthog", "posthog", "")
        assert "-- @section: step_0" in up_sql
        assert "-- @section: step_1" in up_sql

    def test_empty_ops(self):
        result = StandaloneResult(migration_number=3, migration_name="0003_noop", file_path="test.py", operations=[])
        assert "no-op" in generate_up_sql(result, "posthog", "posthog", "")
