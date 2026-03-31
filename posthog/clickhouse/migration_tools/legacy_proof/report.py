"""Generate machine-readable and human-readable proof reports.

Produces per-migration and summary reports from comparison results.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from posthog.clickhouse.migration_tools.legacy_proof.comparator import ComparisonVerdict, MigrationComparison


def generate_report(
    comparisons: list[MigrationComparison],
    output_dir: Path,
    *,
    report_name: str = "proof_report",
) -> Path:
    """Generate both JSON and human-readable text reports.

    Returns path to the report directory.
    """
    report_dir = output_dir / report_name
    report_dir.mkdir(parents=True, exist_ok=True)

    # Machine-readable JSON report
    json_report = _build_json_report(comparisons)
    (report_dir / "report.json").write_text(json.dumps(json_report, indent=2, default=str))

    # Human-readable text report
    text_report = _build_text_report(comparisons)
    (report_dir / "report.txt").write_text(text_report)

    # Summary table
    summary = _build_summary_table(comparisons)
    (report_dir / "summary.txt").write_text(summary)

    return report_dir


def _build_json_report(comparisons: list[MigrationComparison]) -> dict:
    """Build the full machine-readable report."""
    verdicts = Counter(c.verdict.value for c in comparisons)
    classifications = Counter(c.classification for c in comparisons)

    migrations = []
    for cmp in comparisons:
        entry = {
            "migration_number": cmp.migration_number,
            "migration_name": cmp.migration_name,
            "classification": cmp.classification,
            "verdict": cmp.verdict.value,
            "step_count_match": cmp.step_count_match,
            "step_count": len(cmp.step_comparisons),
            "notes": cmp.notes,
            "warnings": cmp.warnings,
            "steps": [],
        }
        for sc in cmp.step_comparisons:
            entry["steps"].append(
                {
                    "index": sc.step_index,
                    "sql_match": sc.sql_match,
                    "normalized_sql_match": sc.normalized_sql_match,
                    "role_match": sc.role_match,
                    "sharded_match": sc.sharded_match,
                    "alter_replicated_match": sc.alter_replicated_match,
                    "legacy_roles": sc.legacy_roles,
                    "generated_roles": sc.generated_roles,
                    "notes": sc.notes,
                }
            )
        migrations.append(entry)

    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "total_migrations": len(comparisons),
        "summary": {
            "by_verdict": dict(verdicts),
            "by_classification": dict(classifications),
            "pass_rate": _pass_rate(comparisons),
        },
        "migrations": migrations,
    }


def _build_text_report(comparisons: list[MigrationComparison]) -> str:
    """Build a human-readable text report."""
    lines = [
        "=" * 80,
        "CLICKHOUSE LEGACY-TO-DECLARATIVE PROOF REPORT",
        f"Generated: {datetime.now(tz=UTC).isoformat()}",
        "=" * 80,
        "",
    ]

    # Summary
    verdicts = Counter(c.verdict.value for c in comparisons)
    classifications = Counter(c.classification for c in comparisons)

    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"Total migrations: {len(comparisons)}")
    lines.append(f"Pass rate: {_pass_rate(comparisons):.1%}")
    lines.append("")

    lines.append("By verdict:")
    for v, count in sorted(verdicts.items()):
        lines.append(f"  {v}: {count}")
    lines.append("")

    lines.append("By classification:")
    for c, count in sorted(classifications.items()):
        lines.append(f"  {c}: {count}")
    lines.append("")

    # Mismatches and manual-review (detailed)
    mismatches = [c for c in comparisons if c.verdict == ComparisonVerdict.MISMATCH]
    manual_reviews = [c for c in comparisons if c.verdict == ComparisonVerdict.MANUAL_REVIEW_NEEDED]

    if mismatches:
        lines.append("=" * 80)
        lines.append(f"MISMATCHES ({len(mismatches)})")
        lines.append("=" * 80)
        for cmp in mismatches:
            lines.extend(_format_comparison_detail(cmp))

    if manual_reviews:
        lines.append("=" * 80)
        lines.append(f"MANUAL REVIEW NEEDED ({len(manual_reviews)})")
        lines.append("=" * 80)
        for cmp in manual_reviews:
            lines.extend(_format_comparison_detail(cmp))

    # Passes (brief)
    passes = [c for c in comparisons if c.verdict in (ComparisonVerdict.EXACT_PASS, ComparisonVerdict.INFERRED_PASS)]
    if passes:
        lines.append("=" * 80)
        lines.append(f"PASSED ({len(passes)})")
        lines.append("=" * 80)
        for cmp in passes:
            lines.append(f"  [{cmp.verdict.value}] {cmp.migration_name} ({len(cmp.step_comparisons)} steps)")

    lines.append("")
    return "\n".join(lines)


def _build_summary_table(comparisons: list[MigrationComparison]) -> str:
    """Build a concise summary table."""
    lines = [
        f"{'#':>4}  {'Name':<50}  {'Class':<15}  {'Verdict':<20}  {'Steps':>5}",
        "-" * 100,
    ]

    for cmp in comparisons:
        lines.append(
            f"{cmp.migration_number:>4}  "
            f"{cmp.migration_name:<50}  "
            f"{cmp.classification:<15}  "
            f"{cmp.verdict.value:<20}  "
            f"{len(cmp.step_comparisons):>5}"
        )

    return "\n".join(lines)


def _format_comparison_detail(cmp: MigrationComparison) -> list[str]:
    """Format detailed info for a single comparison."""
    lines = [
        "",
        f"  {cmp.migration_name} (#{cmp.migration_number})",
        f"    Classification: {cmp.classification}",
        f"    Step count match: {cmp.step_count_match}",
    ]

    if cmp.notes:
        lines.append("    Notes:")
        for note in cmp.notes:
            lines.append(f"      - {note}")

    if cmp.warnings:
        lines.append("    Warnings:")
        for warn in cmp.warnings:
            lines.append(f"      - {warn}")

    for sc in cmp.step_comparisons:
        lines.append(f"    Step {sc.step_index}:")
        lines.append(f"      SQL match: {sc.sql_match} | Normalized: {sc.normalized_sql_match}")
        lines.append(f"      Role match: {sc.role_match} (legacy={sc.legacy_roles}, gen={sc.generated_roles})")
        lines.append(f"      Sharded match: {sc.sharded_match}")
        lines.append(f"      Alter replicated match: {sc.alter_replicated_match}")
        if sc.notes:
            for note in sc.notes:
                lines.append(f"      Note: {note}")

    return lines


def _pass_rate(comparisons: list[MigrationComparison]) -> float:
    """Calculate the pass rate."""
    if not comparisons:
        return 0.0
    passing = sum(
        1 for c in comparisons if c.verdict in (ComparisonVerdict.EXACT_PASS, ComparisonVerdict.INFERRED_PASS)
    )
    return passing / len(comparisons)
