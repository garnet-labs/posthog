import pytest

from posthog.clickhouse.migrations.jinja_env import create_migration_env, render_sql


class TestRenderSql:
    def test_render_simple_variable(self):
        result = render_sql(
            "CREATE TABLE {{ database }}.foo ENGINE = MergeTree()",
            {"database": "posthog"},
        )

        assert result == "CREATE TABLE posthog.foo ENGINE = MergeTree()"

    def test_render_multiple_variables(self):
        result = render_sql(
            "CREATE TABLE {{ database }}.foo ON CLUSTER '{{ cluster }}'",
            {"database": "posthog", "cluster": "posthog_cluster"},
        )

        assert result == "CREATE TABLE posthog.foo ON CLUSTER 'posthog_cluster'"

    def test_reject_block_tags(self):
        with pytest.raises(ValueError, match="block"):
            render_sql(
                "{% for i in range(10) %}SELECT {{ i }};{% endfor %}",
                {},
            )

    def test_reject_comment_tags(self):
        with pytest.raises(ValueError, match="comment"):
            render_sql(
                "SELECT 1; {# this is a comment #}",
                {},
            )

    def test_reject_invalid_variable_name(self):
        with pytest.raises(ValueError, match="variable"):
            render_sql(
                "SELECT {{ __class__ }}",
                {"__class__": "bad"},
            )

    def test_render_with_unknown_variable(self):
        with pytest.raises(Exception):
            render_sql(
                "SELECT {{ undefined_var }}",
                {},
            )

    def test_render_preserves_sql(self):
        sql = "SELECT * FROM events WHERE timestamp > '2024-01-01' AND properties['$browser'] = 'Chrome'"
        result = render_sql(sql, {})

        assert result == sql

    def test_render_preserves_sql_comments(self):
        sql = "-- This is a SQL comment\nSELECT 1;"
        result = render_sql(sql, {})

        assert result == sql


class TestCreateMigrationEnv:
    def test_creates_sandboxed_env(self):
        env = create_migration_env()

        from jinja2.sandbox import SandboxedEnvironment

        assert isinstance(env, SandboxedEnvironment)

    def test_env_undefined_raises(self):
        env = create_migration_env()

        template = env.from_string("{{ missing }}")
        with pytest.raises(Exception):
            template.render({})
