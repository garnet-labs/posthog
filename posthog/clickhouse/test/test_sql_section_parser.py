import pytest

from posthog.clickhouse.migrations.manifest import ManifestStep
from posthog.clickhouse.migrations.sql_parser import get_sql_for_step, parse_sql_sections


class TestParseSqlSections:
    def test_parse_single_section(self):
        content = """\
-- @section: create_table
CREATE TABLE foo (id UInt64) ENGINE = MergeTree() ORDER BY id;
"""
        result = parse_sql_sections(content)

        assert "create_table" in result
        assert "CREATE TABLE foo" in result["create_table"]

    def test_parse_multiple_sections(self):
        content = """\
-- @section: create_local
CREATE TABLE foo_local (id UInt64) ENGINE = ReplicatedMergeTree() ORDER BY id;

-- @section: create_distributed
CREATE TABLE foo AS foo_local ENGINE = Distributed('cluster', 'db', 'foo_local', rand());
"""
        result = parse_sql_sections(content)

        assert len(result) == 2
        assert "create_local" in result
        assert "create_distributed" in result
        assert "ReplicatedMergeTree" in result["create_local"]
        assert "Distributed" in result["create_distributed"]

    def test_parse_no_sections(self):
        content = """\
CREATE TABLE foo (id UInt64) ENGINE = MergeTree() ORDER BY id;
"""
        result = parse_sql_sections(content)

        assert "default" in result
        assert "CREATE TABLE foo" in result["default"]

    def test_parse_section_with_whitespace_variations(self):
        content = """\
--@section:no_spaces
SELECT 1;

-- @section:   extra_spaces
SELECT 2;
"""
        result = parse_sql_sections(content)

        assert "no_spaces" in result
        assert "extra_spaces" in result


class TestGetSqlForStep:
    def test_get_sql_for_step_with_section(self, tmp_path):
        sql_content = """\
-- @section: alter_sharded
ALTER TABLE events ADD COLUMN foo String;

-- @section: alter_distributed
ALTER TABLE events_distributed ADD COLUMN foo String;
"""
        (tmp_path / "up.sql").write_text(sql_content)

        step = ManifestStep(
            sql="up.sql#alter_sharded",
            node_roles=["DATA"],
        )

        result = get_sql_for_step(tmp_path, step)

        assert "ALTER TABLE events ADD COLUMN foo String" in result
        assert "events_distributed" not in result

    def test_get_sql_for_step_without_section(self, tmp_path):
        sql_content = "CREATE TABLE foo (id UInt64) ENGINE = MergeTree() ORDER BY id;\n"
        (tmp_path / "up.sql").write_text(sql_content)

        step = ManifestStep(
            sql="up.sql",
            node_roles=["DATA"],
        )

        result = get_sql_for_step(tmp_path, step)

        assert "CREATE TABLE foo" in result

    def test_get_sql_for_step_missing_section(self, tmp_path):
        sql_content = """\
-- @section: existing_section
SELECT 1;
"""
        (tmp_path / "up.sql").write_text(sql_content)

        step = ManifestStep(
            sql="up.sql#nonexistent",
            node_roles=["DATA"],
        )

        with pytest.raises(KeyError, match="nonexistent"):
            get_sql_for_step(tmp_path, step)

    def test_get_sql_for_step_missing_file(self, tmp_path):
        step = ManifestStep(
            sql="missing.sql",
            node_roles=["DATA"],
        )

        with pytest.raises(FileNotFoundError):
            get_sql_for_step(tmp_path, step)
