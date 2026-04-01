from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from posthog.clickhouse.migration_tools.manifest import MigrationManifest, parse_manifest
from posthog.clickhouse.migration_tools.schema_graph import TableEcosystem, get_ecosystem_by_name, lookup_ecosystem


@dataclass
class ValidationResult:
    rule: str
    severity: str  # "error" or "warning"
    message: str


def validate_migration(migration_dir: Path, *, strict: bool = False) -> list[ValidationResult]:
    manifest = parse_manifest(migration_dir / "manifest.yaml")
    sql_content = _collect_sql_content(migration_dir, manifest)
    stripped_sql = _COMMENT_LINE_RE.sub("", sql_content)

    results: list[ValidationResult] = []
    results.extend(_check_on_cluster(sql_content))
    results.extend(_check_rollback_completeness(manifest))
    results.extend(_check_node_role_consistency(manifest))
    results.extend(_check_drop_statements(stripped_sql, strict=strict))
    results.extend(_check_mutation_on_distributed(stripped_sql))
    results.extend(check_ecosystem_completeness(manifest, stripped_sql))
    results.extend(check_creation_order(stripped_sql))
    results.extend(check_cross_cluster_targeting(manifest))
    return results


def _collect_sql_content(migration_dir: Path, manifest: MigrationManifest) -> str:
    seen_files: set[str] = set()
    parts: list[str] = []

    for step in [*manifest.steps, *manifest.rollback]:
        filename = step.sql.split("#")[0]
        if filename not in seen_files:
            seen_files.add(filename)
            sql_path = migration_dir / filename
            if sql_path.exists():
                parts.append(sql_path.read_text())

    return "\n".join(parts)


_ON_CLUSTER_RE = re.compile(r"\bON\s+CLUSTER\b", re.IGNORECASE)


def _check_on_cluster(sql_content: str) -> list[ValidationResult]:
    """SQL must not contain ON CLUSTER — the migration system handles routing via manifest node_roles."""
    results: list[ValidationResult] = []
    if _ON_CLUSTER_RE.search(sql_content):
        results.append(
            ValidationResult(
                rule="on_cluster",
                severity="error",
                message="SQL contains 'ON CLUSTER'. The migration system handles cluster routing via "
                "manifest node_roles. Remove ON CLUSTER from your SQL.",
            )
        )
    return results


def _check_rollback_completeness(manifest: MigrationManifest) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    n_steps = len(manifest.steps)
    n_rollback = len(manifest.rollback)

    if n_steps > 0 and n_rollback != n_steps:
        results.append(
            ValidationResult(
                rule="rollback_completeness",
                severity="error",
                message=f"Migration has {n_steps} steps but {n_rollback} rollback entries. "
                "Each step should have a corresponding rollback entry.",
            )
        )
    return results


def _check_node_role_consistency(manifest: MigrationManifest) -> list[ValidationResult]:
    results: list[ValidationResult] = []

    for i, step in enumerate(manifest.steps):
        if step.sharded and "DATA" not in step.node_roles:
            results.append(
                ValidationResult(
                    rule="node_role_consistency",
                    severity="warning",
                    message=f"Step {i} is marked sharded=True but does not target DATA role "
                    f"(targets: {step.node_roles}). Sharded operations should include DATA.",
                )
            )

    return results


_DROP_STMT_RE = re.compile(r"^\s*DROP\s+", re.IGNORECASE | re.MULTILINE)
_COMMENT_LINE_RE = re.compile(r"^\s*--.*$", re.MULTILINE)
_UPDATE_DELETE_RE = re.compile(r"^\s*(ALTER\s+TABLE\s+\S+\s+)?(UPDATE|DELETE)\s+", re.IGNORECASE | re.MULTILINE)
_DISTRIBUTED_ENGINE_RE = re.compile(r"ENGINE\s*=\s*Distributed", re.IGNORECASE)


def _check_drop_statements(sql_content: str, *, strict: bool = False) -> list[ValidationResult]:
    results: list[ValidationResult] = []

    if _DROP_STMT_RE.search(sql_content):
        results.append(
            ValidationResult(
                rule="drop_statement",
                severity="error" if strict else "warning",
                message="SQL contains DROP statement(s). Ensure this is intentional and "
                "that data loss has been considered.",
            )
        )
    return results


def _check_mutation_on_distributed(sql_content: str) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    if _UPDATE_DELETE_RE.search(sql_content) and _DISTRIBUTED_ENGINE_RE.search(sql_content):
        results.append(
            ValidationResult(
                rule="mutation_on_distributed",
                severity="warning",
                message="SQL contains UPDATE/DELETE alongside Distributed engine tables. "
                "Mutations should target the local MergeTree table, not the Distributed table.",
            )
        )
    return results


# Matches CREATE TABLE, ALTER TABLE, DROP TABLE followed by optional IF [NOT] EXISTS and table name
_TABLE_REF_RE = re.compile(
    r"\b(CREATE|ALTER|DROP)\s+(?:TABLE|MATERIALIZED\s+VIEW|VIEW|DICTIONARY)"
    r"(?:\s+IF\s+(?:NOT\s+)?EXISTS)?"
    r"\s+(?:`?[\w]+`?\.)?`?([\w]+)`?",
    re.IGNORECASE,
)


def _extract_table_refs(sql_content: str) -> set[str]:
    """Extract table names referenced by CREATE/ALTER/DROP statements."""
    return {match.group(2).lower() for match in _TABLE_REF_RE.finditer(sql_content)}


def check_ecosystem_completeness(manifest: MigrationManifest, sql_content: str) -> list[ValidationResult]:
    """Warn if a migration touches some tables in an ecosystem but not all companions."""
    results: list[ValidationResult] = []
    referenced_tables = _extract_table_refs(sql_content)

    # If manifest declares an ecosystem, use it directly
    checked_ecosystems: set[str] = set()

    if manifest.ecosystem:
        eco = get_ecosystem_by_name(manifest.ecosystem)
        if eco is None:
            results.append(
                ValidationResult(
                    rule="ecosystem_completeness",
                    severity="warning",
                    message=f"Manifest declares ecosystem '{manifest.ecosystem}' but no such "
                    "ecosystem is defined in schema_graph.py.",
                )
            )
            return results
        checked_ecosystems.add(eco.base_name)
        _check_one_ecosystem(eco, referenced_tables, results)

    # Also check any ecosystems inferred from SQL table references
    for table_name in referenced_tables:
        eco = lookup_ecosystem(table_name)
        if eco and eco.base_name not in checked_ecosystems:
            checked_ecosystems.add(eco.base_name)
            _check_one_ecosystem(eco, referenced_tables, results)

    return results


def _check_one_ecosystem(
    eco: TableEcosystem,
    referenced_tables: set[str],
    results: list[ValidationResult],
) -> None:
    eco_tables = eco.all_tables()
    present = referenced_tables & {t.lower() for t in eco_tables}
    missing = {t for t in eco_tables if t.lower() not in referenced_tables}

    if present and missing:
        results.append(
            ValidationResult(
                rule="ecosystem_completeness",
                severity="warning",
                message=f"This migration modifies tables in the '{eco.base_name}' ecosystem "
                f"({', '.join(sorted(present))}) but does not touch: "
                f"{', '.join(sorted(missing))}. "
                f"Consider whether companion tables also need updating.",
            )
        )


# Per-statement regexes (applied to individual SQL statements, not the full file)
_CREATE_NAME_RE = re.compile(
    r"CREATE\s+(?:TABLE|MATERIALIZED\s+VIEW|DICTIONARY)"
    r"(?:\s+IF\s+NOT\s+EXISTS)?"
    r"\s+(?:`?[\w]+`?\.)?`?([\w]+)`?",
    re.IGNORECASE,
)

_ENGINE_RE = re.compile(r"ENGINE\s*=\s*([\w]+)", re.IGNORECASE)

_MV_TO_RE = re.compile(r"\bTO\s+(?:`?[\w]+`?\.)?`?[\w]+`?", re.IGNORECASE)

# Engine type -> dependency tier (lower tier must be created first)
_ENGINE_TIER: dict[str, int] = {
    "kafka": 0,
    "mergetree": 1,
    "replacingmergetree": 1,
    "aggregatingmergetree": 1,
    "collapsingmergetree": 1,
    "replicatedmergetree": 1,
    "replicatedreplacingmergetree": 1,
    "replicatedaggregatingmergetree": 1,
    "replicatedcollapsingmergetree": 1,
    "distributed": 2,
    "materializedview": 3,
    "dictionary": 3,
}


def _classify_engine(engine: str) -> int:
    """Return dependency tier for an engine type. Unknown engines get tier 1 (neutral)."""
    return _ENGINE_TIER.get(engine.lower(), 1)


def _classify_create_statement(stmt: str) -> tuple[str, int] | None:
    """Extract (table_name, tier) from a single CREATE statement, or None if not a CREATE."""
    name_match = _CREATE_NAME_RE.search(stmt)
    if not name_match:
        return None

    table_name = name_match.group(1)

    # Check for MV with TO syntax (no ENGINE keyword needed)
    is_mv = re.search(r"CREATE\s+MATERIALIZED\s+VIEW", stmt, re.IGNORECASE)
    if is_mv and _MV_TO_RE.search(stmt):
        return (table_name, 3)

    # Check for ENGINE = <type>
    engine_match = _ENGINE_RE.search(stmt)
    if engine_match:
        return (table_name, _classify_engine(engine_match.group(1)))

    return None


def check_creation_order(sql_content: str) -> list[ValidationResult]:
    """Verify CREATEs appear in dependency order: Kafka(0) -> MergeTree(1) -> Distributed(2) -> MV/Dict(3)."""
    results: list[ValidationResult] = []

    # Split into statements and classify each one
    statements = [s.strip() for s in sql_content.split(";") if s.strip()]
    creates: list[tuple[str, int]] = []
    seen: set[str] = set()

    for stmt in statements:
        classified = _classify_create_statement(stmt)
        if classified:
            name, tier = classified
            lower_name = name.lower()
            if lower_name not in seen:
                seen.add(lower_name)
                creates.append((name, tier))

    # Check ordering: each item's tier should be >= all previous tiers
    max_tier_so_far = -1
    max_tier_name = ""
    for name, tier in creates:
        if tier < max_tier_so_far:
            results.append(
                ValidationResult(
                    rule="creation_order",
                    severity="error",
                    message=f"'{name}' (tier {tier}) is created after '{max_tier_name}' "
                    f"(tier {max_tier_so_far}). Objects must be created in dependency order: "
                    f"Kafka(0) -> MergeTree(1) -> Distributed(2) -> MV/Dict(3).",
                )
            )
            break  # One error is enough to flag the problem
        if tier > max_tier_so_far:
            max_tier_so_far = tier
            max_tier_name = name

    return results


def check_cross_cluster_targeting(manifest: MigrationManifest) -> list[ValidationResult]:
    """Check that steps target appropriate node roles for their operation type."""
    results: list[ValidationResult] = []

    for i, step in enumerate(manifest.steps):
        comment_lower = step.comment.lower() if step.comment else ""
        sql_ref = step.sql.lower()

        # If the step comment or sql ref mentions "distributed", it likely creates
        # a distributed table — these belong on COORDINATOR nodes
        is_distributed_hint = "distributed" in comment_lower or "distributed" in sql_ref

        if is_distributed_hint and "COORDINATOR" not in step.node_roles:
            results.append(
                ValidationResult(
                    rule="cross_cluster_targeting",
                    severity="warning",
                    message=f"Step {i} appears to involve a Distributed table "
                    f"(hint: '{step.comment or step.sql}') but targets {step.node_roles}. "
                    f"Distributed tables typically belong on COORDINATOR nodes.",
                )
            )

        # Already covered by node_role_consistency, but cross-cluster variant:
        # if a step targets specific clusters, DATA steps should match the data cluster
        if step.sharded and step.clusters:
            if "DATA" not in step.node_roles:
                results.append(
                    ValidationResult(
                        rule="cross_cluster_targeting",
                        severity="warning",
                        message=f"Step {i} is sharded and targets clusters {step.clusters} "
                        f"but does not include DATA in node_roles ({step.node_roles}).",
                    )
                )

    return results
