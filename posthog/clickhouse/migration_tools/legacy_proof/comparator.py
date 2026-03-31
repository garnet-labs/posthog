"""Compare legacy and generated migration representations.

Implements the acceptance bar from the design spec:
- final schema matches legacy result
- effective execution order matches legacy intent
- effective host/role targeting matches legacy intent
- tracking state is comparable
- rendered SQL is close enough to justify equivalence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import yaml

from posthog.clickhouse.migration_tools.legacy_proof.extractor import ExtractedOperation, ExtractionResult
from posthog.clickhouse.migration_tools.legacy_proof.generator import GeneratedArtifact
from posthog.clickhouse.migration_tools.legacy_proof.normalizer import normalize_node_roles, normalize_sql


class ComparisonVerdict(str, Enum):
    EXACT_PASS = "exact_pass"
    INFERRED_PASS = "inferred_pass"
    MANUAL_REVIEW_NEEDED = "manual_review_needed"
    MISMATCH = "mismatch"


@dataclass
class StepComparison:
    """Comparison result for a single step."""

    step_index: int
    sql_match: bool = False
    normalized_sql_match: bool = False
    role_match: bool = False
    sharded_match: bool = False
    alter_replicated_match: bool = False
    legacy_sql: str = ""
    generated_sql: str = ""
    legacy_roles: list[str] = field(default_factory=list)
    generated_roles: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class MigrationComparison:
    """Full comparison result for one migration."""

    migration_number: int
    migration_name: str
    classification: str
    step_count_match: bool
    step_comparisons: list[StepComparison] = field(default_factory=list)
    verdict: ComparisonVerdict = ComparisonVerdict.MISMATCH
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def compare_migration(
    extraction: ExtractionResult,
    artifact: GeneratedArtifact,
) -> MigrationComparison:
    """Compare a legacy extraction against its generated declarative artifact.

    Returns a detailed comparison result including per-step SQL, role, and
    metadata comparisons.
    """
    result = MigrationComparison(
        migration_number=extraction.migration_number,
        migration_name=extraction.migration_name,
        classification=extraction.classification,
        step_count_match=True,
    )

    # Parse generated manifest to get step count
    manifest_data = yaml.safe_load(artifact.manifest_yaml)
    generated_steps = manifest_data.get("steps", [])
    legacy_op_count = len(extraction.operations)
    generated_step_count = len(generated_steps)

    # Handle no-op migrations
    if legacy_op_count == 0 and generated_step_count <= 1:
        result.step_count_match = True
        result.verdict = ComparisonVerdict.EXACT_PASS
        result.notes.append("No-op migration — both sides empty or single no-op step")
        return result

    if legacy_op_count != generated_step_count:
        result.step_count_match = False
        result.notes.append(f"Step count mismatch: legacy={legacy_op_count}, generated={generated_step_count}")

    # Parse generated up.sql to get per-step SQL
    generated_sql_sections = _parse_generated_sql(artifact.up_sql, generated_step_count)

    # Compare each step
    all_pass = True
    for i, op in enumerate(extraction.operations):
        gen_step = generated_steps[i] if i < generated_step_count else None
        gen_sql = generated_sql_sections.get(i, "")

        step_cmp = _compare_step(i, op, gen_step, gen_sql)
        result.step_comparisons.append(step_cmp)

        if not (
            step_cmp.normalized_sql_match
            and step_cmp.role_match
            and step_cmp.sharded_match
            and step_cmp.alter_replicated_match
        ):
            all_pass = False

    # Determine verdict
    if extraction.classification == "manual-review":
        result.verdict = ComparisonVerdict.MANUAL_REVIEW_NEEDED
    elif all_pass and result.step_count_match:
        if extraction.classification == "exact":
            result.verdict = ComparisonVerdict.EXACT_PASS
        else:
            result.verdict = ComparisonVerdict.INFERRED_PASS
    elif not result.step_count_match:
        result.verdict = ComparisonVerdict.MISMATCH
        result.notes.append("Step count mismatch prevents pass verdict")
    else:
        result.verdict = ComparisonVerdict.MISMATCH

    result.warnings = list(extraction.warnings)
    return result


def _compare_step(
    index: int,
    legacy_op: ExtractedOperation,
    gen_step: dict | None,
    gen_sql: str,
) -> StepComparison:
    """Compare a single step between legacy and generated."""
    cmp = StepComparison(step_index=index)
    cmp.legacy_sql = legacy_op.sql
    cmp.generated_sql = gen_sql

    if gen_step is None:
        cmp.notes.append("No corresponding generated step")
        return cmp

    # SQL comparison
    cmp.sql_match = legacy_op.sql.strip() == gen_sql.strip()
    norm_legacy = normalize_sql(legacy_op.sql)
    norm_generated = normalize_sql(gen_sql)
    cmp.normalized_sql_match = norm_legacy == norm_generated

    if not cmp.normalized_sql_match and not cmp.sql_match:
        # Check if it's just templatization differences
        # The generator replaces hardcoded values with {{ var }}
        # For comparison, we allow this as equivalent
        cmp.normalized_sql_match = _is_template_equivalent(norm_legacy, norm_generated)
        if cmp.normalized_sql_match:
            cmp.notes.append("SQL matches after accounting for template variable substitution")

    # Role comparison
    legacy_roles = normalize_node_roles(legacy_op.node_roles)
    gen_roles = normalize_node_roles(gen_step.get("node_roles", []))
    cmp.legacy_roles = sorted(legacy_roles)
    cmp.generated_roles = sorted(gen_roles)
    cmp.role_match = legacy_roles == gen_roles

    # Metadata comparison
    cmp.sharded_match = legacy_op.sharded == gen_step.get("sharded", False)
    cmp.alter_replicated_match = legacy_op.is_alter_on_replicated_table == gen_step.get(
        "is_alter_on_replicated_table", False
    )

    return cmp


def _parse_generated_sql(up_sql: str, step_count: int) -> dict[int, str]:
    """Parse generated up.sql into per-step SQL sections."""
    import re

    sections: dict[int, str] = {}

    # Try section-based parsing first
    section_pattern = re.compile(r"^--\s*@section:\s*step_(\d+)\s*$", re.MULTILINE)
    matches = list(section_pattern.finditer(up_sql))

    if matches:
        for i, match in enumerate(matches):
            idx = int(match.group(1))
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(up_sql)
            sections[idx] = up_sql[start:end].strip()
    elif step_count <= 1:
        # Single step, whole file is the SQL
        sections[0] = up_sql.strip()

    return sections


def _is_template_equivalent(norm_legacy: str, norm_generated: str) -> bool:
    """Check if two normalized SQL strings are equivalent modulo Jinja2 templates.

    The generator replaces hardcoded database/cluster names with {{ var }},
    which is an expected and valid transformation.
    """
    import re

    # Replace {{ var }} in generated with a placeholder
    cleaned_generated = re.sub(r"\{\{\s*\w+\s*\}\}", "__TMPL__", norm_generated)
    # Replace known literal values in legacy with same placeholder
    try:
        from django.conf import settings

        db = getattr(settings, "CLICKHOUSE_DATABASE", "posthog")
        cluster = getattr(settings, "CLICKHOUSE_CLUSTER", "posthog")
        single_shard = getattr(settings, "CLICKHOUSE_SINGLE_SHARD_CLUSTER", "")
    except Exception:
        db = "posthog"
        cluster = "posthog"
        single_shard = ""

    cleaned_legacy = norm_legacy
    for val in [db, cluster, single_shard]:
        if val:
            cleaned_legacy = cleaned_legacy.replace(f"'{val}'", "'__TMPL__'")
            cleaned_legacy = re.sub(
                rf"(?<![a-zA-Z0-9_]){re.escape(val)}(?=\.)",
                "__TMPL__",
                cleaned_legacy,
            )

    return cleaned_legacy == cleaned_generated


def compare_all(
    extractions: list[ExtractionResult],
    artifacts: list[GeneratedArtifact],
) -> list[MigrationComparison]:
    """Compare all legacy extractions against their generated artifacts."""
    # Build lookup by migration number
    artifact_map = {a.migration_number: a for a in artifacts}

    results = []
    for extraction in extractions:
        artifact = artifact_map.get(extraction.migration_number)
        if artifact is None:
            results.append(
                MigrationComparison(
                    migration_number=extraction.migration_number,
                    migration_name=extraction.migration_name,
                    classification=extraction.classification,
                    step_count_match=False,
                    verdict=ComparisonVerdict.MISMATCH,
                    notes=["No generated artifact found"],
                )
            )
            continue

        results.append(compare_migration(extraction, artifact))

    return results
