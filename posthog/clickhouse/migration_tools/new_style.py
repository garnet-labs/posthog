from __future__ import annotations

from pathlib import Path

from posthog.clickhouse.migration_tools.jinja_env import render_sql
from posthog.clickhouse.migration_tools.manifest import ManifestStep, MigrationManifest, parse_manifest
from posthog.clickhouse.migration_tools.sql_parser import get_sql_for_step


def _get_template_variables() -> dict[str, str]:
    """Deferred import to avoid requiring Django at module load time."""
    from django.conf import settings

    return {
        "database": settings.CLICKHOUSE_DATABASE,
        "cluster": settings.CLICKHOUSE_CLUSTER,
        "single_shard_cluster": getattr(settings, "CLICKHOUSE_SINGLE_SHARD_CLUSTER", ""),
    }


class NewStyleMigration:
    """A directory-based ClickHouse migration: manifest.yaml + *.sql templates."""

    def __init__(self, migration_dir: Path) -> None:
        self.dir = migration_dir
        self.manifest: MigrationManifest = parse_manifest(migration_dir / "manifest.yaml")

    def _resolve_steps(self, steps: list[ManifestStep]) -> list[tuple[ManifestStep, str]]:
        variables = _get_template_variables()
        file_cache: dict[str, str] = {}
        result: list[tuple[ManifestStep, str]] = []
        for step in steps:
            raw_sql = get_sql_for_step(self.dir, step, file_cache=file_cache)
            rendered = render_sql(raw_sql, variables)
            result.append((step, rendered))
        return result

    def _resolve_template_steps(self, generated: list[tuple[ManifestStep, str]]) -> list[tuple[ManifestStep, str]]:
        variables = _get_template_variables()
        result: list[tuple[ManifestStep, str]] = []
        for step, raw_sql in generated:
            rendered = render_sql(raw_sql, variables)
            result.append((step, rendered))
        return result

    def get_steps(self) -> list[tuple[ManifestStep, str]]:
        if self.manifest.template:
            from posthog.clickhouse.migration_tools.templates import generate_steps

            generated = generate_steps(self.manifest.template, self.manifest.template_config or {})
            return self._resolve_template_steps(generated)
        return self._resolve_steps(self.manifest.steps)

    def get_rollback_steps(self) -> list[tuple[ManifestStep, str]]:
        if self.manifest.template:
            from posthog.clickhouse.migration_tools.templates import generate_rollback_steps

            generated = generate_rollback_steps(self.manifest.template, self.manifest.template_config or {})
            return self._resolve_template_steps(generated)
        return self._resolve_steps(self.manifest.rollback)
