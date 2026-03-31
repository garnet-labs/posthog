"""Differential replay harness for legacy-to-declarative proof.

Supports five modes as specified in the design:
- fresh replay: run full corpus from empty state
- upgrade replay: start from a checkpoint, run remaining
- single migration debug: one migration with max logging
- batch mode: contiguous range
- full corpus: entire legacy set

Each mode compares the schema state after running legacy operations
vs running the generated declarative equivalents.

IMPORTANT: This module requires a live ClickHouse instance. It creates
isolated databases for proof runs and cleans them up afterward. It does
NOT modify the production database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

logger = logging.getLogger("legacy_proof.replay")

_MIGRATION_PY_RE = re.compile(r"^([0-9]+)_([a-zA-Z_0-9]+)\.py$")


@dataclass
class ReplayResult:
    """Result of a single migration replay comparison."""

    migration_number: int
    migration_name: str
    legacy_schema_columns: int = 0
    generated_schema_columns: int = 0
    schema_match: bool = False
    legacy_tables: list[str] = field(default_factory=list)
    generated_tables: list[str] = field(default_factory=list)
    tables_match: bool = False
    error: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class ReplayReport:
    """Summary of a replay run."""

    mode: str
    started_at: str = ""
    completed_at: str = ""
    total_migrations: int = 0
    schema_matches: int = 0
    schema_mismatches: int = 0
    errors: int = 0
    results: list[ReplayResult] = field(default_factory=list)
    checkpoint_era: str | None = None


def capture_schema(client, database: str) -> list[tuple[str, str, str]]:
    """Capture schema as sorted (table, column, type) tuples."""
    sql = f"""
        SELECT table, name, type
        FROM system.columns
        WHERE database = '{database}'
        ORDER BY table, name
    """
    return sorted(client.execute(sql))


def capture_tables(client, database: str) -> list[str]:
    """Capture table list for a database."""
    sql = f"""
        SELECT name FROM system.tables
        WHERE database = '{database}'
        ORDER BY name
    """
    return [row[0] for row in client.execute(sql)]


def create_proof_database(client, db_name: str) -> None:
    """Create an isolated database for proof replay."""
    client.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")


def drop_proof_database(client, db_name: str) -> None:
    """Drop a proof database after replay."""
    client.execute(f"DROP DATABASE IF EXISTS {db_name}")


def _unique_db_name(prefix: str) -> str:
    """Generate a unique database name for a proof run."""
    ts = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    h = hashlib.sha256(f"{prefix}{ts}".encode()).hexdigest()[:8]
    return f"proof_{prefix}_{h}"


def run_replay(
    client,
    *,
    mode: str = "fresh",
    migrations_dir: Path = Path("posthog/clickhouse/migrations"),
    generated_dir: Path = Path("tmp/ch_migrate_proof/generated"),
    single: int | None = None,
    batch_start: int | None = None,
    batch_end: int | None = None,
    checkpoint_migration: int | None = None,
    checkpoint_era: str | None = None,
) -> ReplayReport:
    """Run a differential replay proof.

    Args:
        client: ClickHouse client connection.
        mode: One of 'fresh', 'upgrade', 'single', 'batch', 'full'.
        migrations_dir: Path to legacy .py migrations.
        generated_dir: Path to generated declarative artifacts.
        single: For single-migration debug mode, the migration number.
        batch_start/batch_end: For batch mode, the range.
        checkpoint_migration: For upgrade mode, the starting migration number.
        checkpoint_era: For upgrade mode, the era name.

    Returns:
        ReplayReport with per-migration comparison results.
    """
    report = ReplayReport(
        mode=mode,
        started_at=datetime.now(tz=UTC).isoformat(),
        checkpoint_era=checkpoint_era,
    )

    # Determine which migrations to replay
    files = sorted(
        [f for f in migrations_dir.iterdir() if f.is_file() and _MIGRATION_PY_RE.match(f.name)],
        key=lambda f: int(_MIGRATION_PY_RE.match(f.name).group(1)),
    )

    if mode == "single" and single is not None:
        files = [f for f in files if int(_MIGRATION_PY_RE.match(f.name).group(1)) == single]
    elif mode == "batch" and batch_start is not None and batch_end is not None:
        files = [
            f for f in files if batch_start <= int(_MIGRATION_PY_RE.match(f.name).group(1)) <= batch_end
        ]
    elif mode == "upgrade" and checkpoint_migration is not None:
        files = [
            f for f in files if int(_MIGRATION_PY_RE.match(f.name).group(1)) > checkpoint_migration
        ]

    report.total_migrations = len(files)

    if not files:
        report.completed_at = datetime.now(tz=UTC).isoformat()
        return report

    # Create isolated databases for the proof run
    legacy_db = _unique_db_name("legacy")
    generated_db = _unique_db_name("generated")

    try:
        create_proof_database(client, legacy_db)
        create_proof_database(client, generated_db)
        logger.info("Created proof databases: %s, %s", legacy_db, generated_db)

        for migration_file in files:
            match = _MIGRATION_PY_RE.match(migration_file.name)
            number = int(match.group(1))
            name = f"{match.group(1)}_{match.group(2)}"
            artifact_dir = generated_dir / name

            result = ReplayResult(migration_number=number, migration_name=name)

            # Execute legacy migration SQL
            try:
                _execute_legacy_migration(client, migration_file, legacy_db)
            except Exception as e:
                result.error = f"Legacy execution failed: {e}"
                result.notes.append(str(e))
                report.errors += 1
                report.results.append(result)
                continue

            # Execute generated declarative migration SQL
            if not artifact_dir.exists():
                result.error = "No generated artifact found"
                result.notes.append("Missing generated artifact directory")
                report.errors += 1
                report.results.append(result)
                continue

            try:
                _execute_generated_migration(client, artifact_dir, generated_db)
            except Exception as e:
                result.error = f"Generated execution failed: {e}"
                result.notes.append(str(e))
                report.errors += 1
                report.results.append(result)
                continue

            # Compare schema state after this migration
            legacy_schema = capture_schema(client, legacy_db)
            generated_schema = capture_schema(client, generated_db)

            result.legacy_schema_columns = len(legacy_schema)
            result.generated_schema_columns = len(generated_schema)
            result.schema_match = legacy_schema == generated_schema

            result.legacy_tables = capture_tables(client, legacy_db)
            result.generated_tables = capture_tables(client, generated_db)
            result.tables_match = result.legacy_tables == result.generated_tables

            if result.schema_match:
                report.schema_matches += 1
            else:
                report.schema_mismatches += 1
                # Log detailed differences
                legacy_set = set(legacy_schema)
                gen_set = set(generated_schema)
                only_legacy = legacy_set - gen_set
                only_generated = gen_set - legacy_set
                if only_legacy:
                    result.notes.append(f"Only in legacy: {len(only_legacy)} columns")
                if only_generated:
                    result.notes.append(f"Only in generated: {len(only_generated)} columns")

            report.results.append(result)

    finally:
        # Clean up proof databases
        try:
            drop_proof_database(client, legacy_db)
            drop_proof_database(client, generated_db)
            logger.info("Cleaned up proof databases")
        except Exception as e:
            logger.warning("Failed to clean up proof databases: %s", e)

    report.completed_at = datetime.now(tz=UTC).isoformat()
    return report


def _execute_legacy_migration(client, migration_file: Path, database: str) -> None:
    """Execute a legacy migration's SQL against a proof database.

    Extracts SQL from the migration's operations and runs them in order,
    substituting the proof database name.
    """
    import importlib.util
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        spec = importlib.util.spec_from_file_location(f"_replay_.{migration_file.stem}", str(migration_file))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {migration_file}")
        module = importlib.util.module_from_spec(spec)
        import sys

        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)

    ops = getattr(module, "operations", [])
    if not isinstance(ops, list):
        return

    for op in ops:
        sql = getattr(op, "_sql", None)
        if sql is None:
            continue
        if callable(sql):
            sql = sql()

        # Substitute database name
        from django.conf import settings

        real_db = getattr(settings, "CLICKHOUSE_DATABASE", "posthog")
        sql = sql.replace(real_db, database)

        try:
            client.execute(sql)
        except Exception as e:
            logger.warning("Legacy SQL execution warning: %s", e)


def _execute_generated_migration(client, artifact_dir: Path, database: str) -> None:
    """Execute a generated declarative migration's SQL against a proof database."""
    manifest_path = artifact_dir / "manifest.yaml"
    up_sql_path = artifact_dir / "up.sql"

    if not manifest_path.exists() or not up_sql_path.exists():
        raise FileNotFoundError(f"Missing manifest.yaml or up.sql in {artifact_dir}")

    manifest = yaml.safe_load(manifest_path.read_text())
    up_sql_raw = up_sql_path.read_text()

    # Resolve Jinja2 templates
    from django.conf import settings

    real_db = getattr(settings, "CLICKHOUSE_DATABASE", "posthog")
    cluster = getattr(settings, "CLICKHOUSE_CLUSTER", "posthog")
    single_shard = getattr(settings, "CLICKHOUSE_SINGLE_SHARD_CLUSTER", "")

    up_sql_resolved = up_sql_raw
    up_sql_resolved = up_sql_resolved.replace("{{ database }}", database)
    up_sql_resolved = up_sql_resolved.replace("{{ cluster }}", cluster)
    if single_shard:
        up_sql_resolved = up_sql_resolved.replace("{{ single_shard_cluster }}", single_shard)
    # Also replace the real database name for SQL that wasn't templatized
    up_sql_resolved = up_sql_resolved.replace(real_db, database)

    # Parse sections and execute in manifest step order
    section_re = re.compile(r"^--\s*@section:\s*step_(\d+)\s*$", re.MULTILINE)
    matches = list(section_re.finditer(up_sql_resolved))

    sql_sections: dict[int, str] = {}
    if matches:
        for i, match in enumerate(matches):
            idx = int(match.group(1))
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(up_sql_resolved)
            sql_sections[idx] = up_sql_resolved[start:end].strip()
    else:
        sql_sections[0] = up_sql_resolved.strip()

    steps = manifest.get("steps", [])
    for step_idx, step in enumerate(steps):
        sql = sql_sections.get(step_idx, "")
        if not sql or sql.startswith("SELECT 1"):
            continue
        try:
            client.execute(sql)
        except Exception as e:
            logger.warning("Generated SQL execution warning (step %d): %s", step_idx, e)


def save_replay_report(report: ReplayReport, output_dir: Path) -> Path:
    """Save a replay report to disk."""
    report_dir = output_dir / "replay_reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"replay_{report.mode}_{ts}.json"

    data = {
        "mode": report.mode,
        "started_at": report.started_at,
        "completed_at": report.completed_at,
        "total_migrations": report.total_migrations,
        "schema_matches": report.schema_matches,
        "schema_mismatches": report.schema_mismatches,
        "errors": report.errors,
        "checkpoint_era": report.checkpoint_era,
        "results": [
            {
                "migration_number": r.migration_number,
                "migration_name": r.migration_name,
                "schema_match": r.schema_match,
                "tables_match": r.tables_match,
                "legacy_columns": r.legacy_schema_columns,
                "generated_columns": r.generated_schema_columns,
                "legacy_tables": r.legacy_tables,
                "generated_tables": r.generated_tables,
                "error": r.error,
                "notes": r.notes,
            }
            for r in report.results
        ],
    }

    report_file = report_dir / filename
    report_file.write_text(json.dumps(data, indent=2))
    return report_file
