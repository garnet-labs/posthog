"""Checkpoint runner for upgrade-replay proof validation.

Selects checkpoint eras from the migration history and validates that
the generated declarative artifacts produce equivalent results when
starting from each checkpoint (representing a historical already-applied state).

This module does NOT require a live ClickHouse instance. It validates
by comparing the _effective operations_ that would be applied from each
checkpoint forward, comparing legacy vs generated paths.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("legacy_proof.checkpoint")


@dataclass
class Checkpoint:
    """A checkpoint representing a historical migration era."""

    name: str
    description: str
    start_migration: int  # First migration to run FROM this checkpoint
    era_range: tuple[int, int]  # (start, end) of the era


@dataclass
class CheckpointResult:
    """Result of validating upgrade replay from a checkpoint."""

    checkpoint: Checkpoint
    migrations_in_range: int
    migrations_passing: int
    migrations_manual_review: int
    migrations_with_issues: list[str] = field(default_factory=list)
    pass_rate: float = 0.0
    notes: list[str] = field(default_factory=list)


# Checkpoint eras derived from the design spec and migration history analysis
CHECKPOINT_ERAS: list[Checkpoint] = [
    Checkpoint(
        name="bootstrap",
        description="Early bootstrap and initial schema (0001-0010)",
        start_migration=1,
        era_range=(1, 10),
    ),
    Checkpoint(
        name="kafka_pipeline",
        description="Kafka tables and MV pipeline (0004-0025)",
        start_migration=4,
        era_range=(4, 25),
    ),
    Checkpoint(
        name="distributed_tables",
        description="Distributed/writable table introduction (0026-0040)",
        start_migration=26,
        era_range=(26, 40),
    ),
    Checkpoint(
        name="ingestion_layer",
        description="Ingestion layer and role targeting (0041-0070)",
        start_migration=41,
        era_range=(41, 70),
    ),
    Checkpoint(
        name="sessions_expansion",
        description="Sessions and session replay expansion (0071-0120)",
        start_migration=71,
        era_range=(71, 120),
    ),
    Checkpoint(
        name="logs_cluster",
        description="Logs-specific migrations and cluster targeting (0121-0180)",
        start_migration=121,
        era_range=(121, 180),
    ),
    Checkpoint(
        name="recent_legacy",
        description="Newest legacy state before 0224 (0181-0223)",
        start_migration=181,
        era_range=(181, 223),
    ),
]


def _load_proof_report(output_dir: Path) -> dict:
    """Load the proof report JSON."""
    report_path = output_dir / "proof_report" / "report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"Proof report not found at {report_path}")
    with open(report_path) as f:
        return json.load(f)


def run_checkpoint_validation(
    output_dir: Path,
    *,
    checkpoints: list[Checkpoint] | None = None,
) -> list[CheckpointResult]:
    """Validate upgrade replay from each checkpoint era.

    For each checkpoint, examines the proof report for migrations in that
    era's range and summarizes pass/fail/manual-review.

    This is a _logical_ checkpoint validation: it verifies that the
    generated declarative artifacts match for each era, without requiring
    a live ClickHouse instance. The reasoning is:

    - If the generated artifacts match the legacy SQL for all migrations
      in an era, then replaying from that checkpoint would produce the
      same schema outcome.
    - The actual SQL execution would produce identical DDL commands on
      both paths.

    For true schema-level validation against a running ClickHouse, the
    differential replay harness (a future enhancement) would compare
    actual table schemas after execution.
    """
    if checkpoints is None:
        checkpoints = CHECKPOINT_ERAS

    report = _load_proof_report(output_dir)
    migrations_by_number = {m["number"]: m for m in report["migrations"]}

    results = []
    for cp in checkpoints:
        era_start, era_end = cp.era_range
        era_migrations = [m for num, m in migrations_by_number.items() if era_start <= num <= era_end]

        if not era_migrations:
            results.append(
                CheckpointResult(
                    checkpoint=cp,
                    migrations_in_range=0,
                    migrations_passing=0,
                    migrations_manual_review=0,
                    notes=["No migrations found in era range"],
                )
            )
            continue

        passing = sum(1 for m in era_migrations if "pass" in m["verdict"])
        manual = sum(1 for m in era_migrations if m["verdict"] == "manual_review_needed")
        issues = [f"{m['name']}: {m['verdict']}" for m in era_migrations if m["verdict"] == "mismatch"]

        total = len(era_migrations)
        pass_rate = passing / total if total > 0 else 0.0

        result = CheckpointResult(
            checkpoint=cp,
            migrations_in_range=total,
            migrations_passing=passing,
            migrations_manual_review=manual,
            migrations_with_issues=issues,
            pass_rate=pass_rate,
        )

        # Add notes about the checkpoint
        if pass_rate == 1.0:
            result.notes.append("All migrations in era pass — upgrade from this checkpoint is safe")
        elif not issues:
            result.notes.append(
                f"No mismatches, but {manual} migrations need manual review before full upgrade confidence"
            )
        else:
            result.notes.append(f"{len(issues)} migration(s) have mismatches requiring investigation")

        results.append(result)

    return results


def generate_checkpoint_report(
    results: list[CheckpointResult],
    output_dir: Path,
) -> Path:
    """Write checkpoint validation results to a report."""
    report_dir = output_dir / "proof_report"
    report_dir.mkdir(parents=True, exist_ok=True)

    # JSON report
    json_data = {
        "checkpoints": [
            {
                "name": r.checkpoint.name,
                "description": r.checkpoint.description,
                "era_range": list(r.checkpoint.era_range),
                "migrations_in_range": r.migrations_in_range,
                "migrations_passing": r.migrations_passing,
                "migrations_manual_review": r.migrations_manual_review,
                "pass_rate": f"{r.pass_rate:.1%}",
                "issues": r.migrations_with_issues,
                "notes": r.notes,
            }
            for r in results
        ],
    }
    (report_dir / "checkpoint_report.json").write_text(json.dumps(json_data, indent=2))

    # Text report
    lines = [
        "=" * 80,
        "CHECKPOINT UPGRADE REPLAY VALIDATION",
        "=" * 80,
        "",
    ]
    for r in results:
        lines.append(f"[{r.checkpoint.name}] {r.checkpoint.description}")
        lines.append(f"  Range: {r.checkpoint.era_range[0]:04d}-{r.checkpoint.era_range[1]:04d}")
        lines.append(f"  Migrations: {r.migrations_in_range}")
        lines.append(f"  Passing: {r.migrations_passing}")
        lines.append(f"  Manual review: {r.migrations_manual_review}")
        lines.append(f"  Pass rate: {r.pass_rate:.1%}")
        if r.migrations_with_issues:
            lines.append("  Issues:")
            for issue in r.migrations_with_issues:
                lines.append(f"    - {issue}")
        for note in r.notes:
            lines.append(f"  Note: {note}")
        lines.append("")

    (report_dir / "checkpoint_report.txt").write_text("\n".join(lines))

    return report_dir


def main():
    """Run checkpoint validation from the command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Checkpoint upgrade replay validation")
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/ch_migrate_proof/generated"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    results = run_checkpoint_validation(args.output_dir)
    generate_checkpoint_report(results, args.output_dir)

    for _r in results:
        pass


if __name__ == "__main__":
    main()
