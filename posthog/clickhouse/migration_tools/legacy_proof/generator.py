"""Generate declarative proof artifacts from extracted legacy migration operations.

Produces a manifest.yaml + up.sql (+ optional down.sql) for each legacy
migration. Generated artifacts are written to a proof-only directory that
is NOT discovered by the real ``ch_migrate`` runner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from posthog.clickhouse.migration_tools.legacy_proof.extractor import ExtractionResult

# Map legacy NodeRole value strings to manifest uppercase role names.
_VALUE_TO_MANIFEST_ROLE: dict[str, str] = {
    "data": "DATA",
    "coordinator": "COORDINATOR",
    "events": "INGESTION_EVENTS",
    "small": "INGESTION_SMALL",
    "medium": "INGESTION_MEDIUM",
    "shufflehog": "SHUFFLEHOG",
    "endpoints": "ENDPOINTS",
    "logs": "LOGS",
    "all": "ALL",
}

# Regex to detect Jinja-template-style variables already in the SQL
_JINJA_VAR_RE = re.compile(r"\{\{.*?\}\}")

# Settings values we can templatize
_TEMPLATE_REPLACEMENTS: dict[str, str] = {}  # Populated at runtime from Django settings


def _get_template_replacements() -> dict[str, str]:
    """Build pattern → template-variable mapping from Django settings."""
    global _TEMPLATE_REPLACEMENTS
    if _TEMPLATE_REPLACEMENTS:
        return _TEMPLATE_REPLACEMENTS

    try:
        from django.conf import settings

        db = getattr(settings, "CLICKHOUSE_DATABASE", "posthog")
        cluster = getattr(settings, "CLICKHOUSE_CLUSTER", "posthog")
        single_shard = getattr(settings, "CLICKHOUSE_SINGLE_SHARD_CLUSTER", "")
    except Exception:
        db = "posthog"
        cluster = "posthog"
        single_shard = ""

    # Only replace when the value appears as a standalone identifier in SQL
    _TEMPLATE_REPLACEMENTS = {}
    if db:
        _TEMPLATE_REPLACEMENTS[db] = "database"
    if cluster:
        _TEMPLATE_REPLACEMENTS[cluster] = "cluster"
    if single_shard:
        _TEMPLATE_REPLACEMENTS[single_shard] = "single_shard_cluster"

    return _TEMPLATE_REPLACEMENTS


def _templatize_sql(sql: str) -> str:
    """Replace hardcoded settings values with Jinja2 template variables.

    Only replaces values that appear in SQL contexts where they represent
    database/cluster names, not random substrings.
    """
    if _JINJA_VAR_RE.search(sql):
        # Already has templates, skip
        return sql

    replacements = _get_template_replacements()
    result = sql

    for literal, var_name in replacements.items():
        if not literal:
            continue
        # Replace database.table patterns: posthog.table -> {{ database }}.table
        result = re.sub(
            rf"(?<![a-zA-Z0-9_]){re.escape(literal)}(?=\.)",
            f"{{{{ {var_name} }}}}",
            result,
        )
        # Replace 'cluster_name' in ON CLUSTER or other quoted contexts
        result = re.sub(
            rf"'{re.escape(literal)}'",
            f"'{{{{ {var_name} }}}}'",
            result,
        )

    return result


def _map_roles(role_values: list[str]) -> list[str]:
    """Convert NodeRole value strings to manifest role names."""
    result = []
    for val in role_values:
        manifest_role = _VALUE_TO_MANIFEST_ROLE.get(val)
        if manifest_role:
            result.append(manifest_role)
        else:
            result.append(val.upper())
    return result


@dataclass
class GeneratedArtifact:
    """One generated declarative proof artifact."""

    migration_number: int
    migration_name: str
    classification: str
    manifest_yaml: str
    up_sql: str
    down_sql: str
    warnings: list[str] = field(default_factory=list)
    source_file: str = ""


def generate_artifact(extraction: ExtractionResult) -> GeneratedArtifact:
    """Convert an ExtractionResult into a declarative proof artifact."""
    artifact = GeneratedArtifact(
        migration_number=extraction.migration_number,
        migration_name=extraction.migration_name,
        classification=extraction.classification,
        manifest_yaml="",
        up_sql="",
        down_sql="",
        warnings=list(extraction.warnings),
        source_file=extraction.file_path,
    )

    if extraction.error:
        artifact.warnings.append(f"Extraction error: {extraction.error}")

    if not extraction.operations:
        # No-op migration or failed extraction
        artifact.manifest_yaml = yaml.dump(
            {
                "description": f"[{extraction.classification}] {extraction.migration_name} (no-op)",
                "steps": [
                    {
                        "sql": "up.sql",
                        "node_roles": ["ALL"],
                        "comment": "No-op migration (empty operations list)",
                    }
                ],
                "rollback": [
                    {
                        "sql": "down.sql",
                        "node_roles": ["ALL"],
                        "comment": "No-op rollback",
                    }
                ],
            },
            default_flow_style=False,
            sort_keys=False,
        )
        artifact.up_sql = "SELECT 1; -- no-op"
        artifact.down_sql = "SELECT 1; -- no-op rollback"
        return artifact

    # Build manifest steps and SQL sections
    steps = []
    up_sections: list[str] = []
    use_sections = len(extraction.operations) > 1

    for op in extraction.operations:
        section_name = f"step_{op.index}"
        sql_ref = f"up.sql#{section_name}" if use_sections else "up.sql"

        step: dict = {
            "sql": sql_ref,
            "node_roles": _map_roles(op.node_roles),
        }
        if op.sharded:
            step["sharded"] = True
        if op.is_alter_on_replicated_table:
            step["is_alter_on_replicated_table"] = True

        steps.append(step)

        templatized_sql = _templatize_sql(op.sql)
        if use_sections:
            up_sections.append(f"-- @section: {section_name}\n{templatized_sql}")
        else:
            up_sections.append(templatized_sql)

    # Build rollback steps (empty stubs — legacy didn't have rollback)
    rollback_steps = []
    for i, op in enumerate(extraction.operations):
        section_name = f"step_{i}"
        sql_ref = f"down.sql#{section_name}" if use_sections else "down.sql"
        rollback_steps.append(
            {
                "sql": sql_ref,
                "node_roles": _map_roles(op.node_roles),
                "comment": "Rollback not derivable from legacy migration",
            }
        )

    manifest_data = {
        "description": f"[{extraction.classification}] {extraction.migration_name}",
        "steps": steps,
        "rollback": rollback_steps,
    }

    artifact.manifest_yaml = yaml.dump(manifest_data, default_flow_style=False, sort_keys=False)
    artifact.up_sql = "\n\n".join(up_sections)

    # Generate stub down.sql
    if use_sections:
        down_sections = [
            f"-- @section: step_{i}\nSELECT 1; -- rollback not derivable from legacy migration"
            for i in range(len(extraction.operations))
        ]
        artifact.down_sql = "\n\n".join(down_sections)
    else:
        artifact.down_sql = "SELECT 1; -- rollback not derivable from legacy migration"

    return artifact


def write_artifact(artifact: GeneratedArtifact, output_dir: Path) -> Path:
    """Write a generated artifact to disk.

    Creates: <output_dir>/<migration_name>/manifest.yaml, up.sql, down.sql
    Returns the artifact directory path.
    """
    artifact_dir = output_dir / artifact.migration_name
    artifact_dir.mkdir(parents=True, exist_ok=True)

    (artifact_dir / "manifest.yaml").write_text(artifact.manifest_yaml)
    (artifact_dir / "up.sql").write_text(artifact.up_sql)
    (artifact_dir / "down.sql").write_text(artifact.down_sql)

    # Write metadata
    meta = {
        "migration_number": artifact.migration_number,
        "migration_name": artifact.migration_name,
        "classification": artifact.classification,
        "warnings": artifact.warnings,
        "source_file": artifact.source_file,
        "step_count": len(yaml.safe_load(artifact.manifest_yaml).get("steps", [])),
    }
    meta_yaml = yaml.dump(meta, default_flow_style=False, sort_keys=False)
    (artifact_dir / "proof_metadata.yaml").write_text(meta_yaml)

    return artifact_dir


def generate_all(
    extractions: list[ExtractionResult],
    output_dir: Path,
) -> list[GeneratedArtifact]:
    """Generate and write declarative proof artifacts for all extractions."""
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []

    for extraction in extractions:
        artifact = generate_artifact(extraction)
        write_artifact(artifact, output_dir)
        artifacts.append(artifact)

    return artifacts
