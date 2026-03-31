"""Main entry point for running the legacy-to-declarative proof pipeline.

Usage (from repo root, with Django configured):

    python -m posthog.clickhouse.migration_tools.legacy_proof.run_proof [options]

Options:
    --migrations-dir PATH   Legacy migration directory (default: posthog/clickhouse/migrations)
    --output-dir PATH       Proof output directory (default: tmp/ch_migrate_proof)
    --single NUMBER         Run proof for a single migration number only
    --batch START END       Run proof for a range of migration numbers
    --report-only           Skip generation, only compare existing artifacts
    --verbose               Verbose output
"""

from __future__ import annotations

import os
import json
import logging
import argparse
from pathlib import Path

logger = logging.getLogger("legacy_proof")


def _setup_django():
    """Configure Django settings if not already configured."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "posthog.settings")
    import django

    django.setup()


def run_proof(
    migrations_dir: Path,
    output_dir: Path,
    *,
    single: int | None = None,
    batch_start: int | None = None,
    batch_end: int | None = None,
    report_only: bool = False,
    verbose: bool = False,
) -> dict:
    """Run the full proof pipeline.

    Returns a summary dict suitable for JSON serialization.
    """
    import re

    from posthog.clickhouse.migration_tools.legacy_proof.comparator import compare_all
    from posthog.clickhouse.migration_tools.legacy_proof.extractor import extract_all_migrations, extract_migration
    from posthog.clickhouse.migration_tools.legacy_proof.generator import generate_all
    from posthog.clickhouse.migration_tools.legacy_proof.report import generate_report

    _MIGRATION_PY_RE = re.compile(r"^([0-9]+)_([a-zA-Z_0-9]+)\.py$")

    # Step 1: Extract legacy migrations
    logger.info("Step 1: Extracting legacy migrations from %s", migrations_dir)

    if single is not None:
        # Single migration mode
        files = [
            f
            for f in sorted(migrations_dir.iterdir())
            if f.is_file() and _MIGRATION_PY_RE.match(f.name) and int(_MIGRATION_PY_RE.match(f.name).group(1)) == single
        ]
        if not files:
            logger.error("Migration %04d not found", single)
            return {"error": f"Migration {single:04d} not found"}
        from posthog.clickhouse.migration_tools.legacy_proof.extractor import extract_migration

        extractions = [extract_migration(files[0])]
    elif batch_start is not None and batch_end is not None:
        # Batch mode
        files = [
            f
            for f in sorted(migrations_dir.iterdir())
            if f.is_file()
            and _MIGRATION_PY_RE.match(f.name)
            and batch_start <= int(_MIGRATION_PY_RE.match(f.name).group(1)) <= batch_end
        ]
        extractions = []
        for f in files:
            extractions.append(extract_migration(f))
    else:
        # Full corpus
        extractions = extract_all_migrations(migrations_dir)

    logger.info("Extracted %d migrations", len(extractions))

    # Step 2: Generate declarative artifacts
    if not report_only:
        logger.info("Step 2: Generating declarative proof artifacts to %s", output_dir)
        artifacts = generate_all(extractions, output_dir / "generated")
        logger.info("Generated %d artifacts", len(artifacts))
    else:
        # Load existing artifacts
        logger.info("Step 2: Loading existing artifacts from %s", output_dir / "generated")
        artifacts = _load_existing_artifacts(extractions, output_dir / "generated")

    # Step 3: Compare
    logger.info("Step 3: Comparing legacy vs generated")
    comparisons = compare_all(extractions, artifacts)
    logger.info("Compared %d migrations", len(comparisons))

    # Step 4: Generate report
    logger.info("Step 4: Generating report")
    report_dir = generate_report(comparisons, output_dir)
    logger.info("Report written to %s", report_dir)

    # Build summary
    from collections import Counter

    verdicts = Counter(c.verdict.value for c in comparisons)
    classifications = Counter(c.classification for c in comparisons)

    passing = sum(1 for c in comparisons if "pass" in c.verdict.value)
    pass_rate = passing / len(comparisons) if comparisons else 0.0

    summary = {
        "total_migrations": len(comparisons),
        "pass_rate": f"{pass_rate:.1%}",
        "by_verdict": dict(verdicts),
        "by_classification": dict(classifications),
        "output_dir": str(output_dir),
        "report_dir": str(report_dir),
    }

    logger.info("Summary: %s", json.dumps(summary, indent=2))
    return summary


def _load_existing_artifacts(extractions, generated_dir: Path):
    """Load previously generated artifacts for report-only mode."""
    from posthog.clickhouse.migration_tools.legacy_proof.generator import GeneratedArtifact

    artifacts = []
    for ext in extractions:
        artifact_dir = generated_dir / ext.migration_name
        if not artifact_dir.exists():
            continue

        manifest_yaml = (
            (artifact_dir / "manifest.yaml").read_text() if (artifact_dir / "manifest.yaml").exists() else ""
        )
        up_sql = (artifact_dir / "up.sql").read_text() if (artifact_dir / "up.sql").exists() else ""
        down_sql = (artifact_dir / "down.sql").read_text() if (artifact_dir / "down.sql").exists() else ""

        import yaml

        meta_path = artifact_dir / "proof_metadata.yaml"
        classification = ext.classification
        if meta_path.exists():
            meta = yaml.safe_load(meta_path.read_text())
            classification = meta.get("classification", classification)

        artifacts.append(
            GeneratedArtifact(
                migration_number=ext.migration_number,
                migration_name=ext.migration_name,
                classification=classification,
                manifest_yaml=manifest_yaml,
                up_sql=up_sql,
                down_sql=down_sql,
                warnings=[],
                source_file=ext.file_path,
            )
        )

    return artifacts


def main():
    parser = argparse.ArgumentParser(description="Legacy-to-declarative migration proof pipeline")
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=Path("posthog/clickhouse/migrations"),
        help="Legacy migration directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/ch_migrate_proof"),
        help="Proof output directory",
    )
    parser.add_argument(
        "--single",
        type=int,
        default=None,
        help="Run proof for a single migration number",
    )
    parser.add_argument(
        "--batch",
        nargs=2,
        type=int,
        default=None,
        metavar=("START", "END"),
        help="Run proof for a range of migration numbers",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Skip generation, only compare existing artifacts",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    _setup_django()

    batch_start = args.batch[0] if args.batch else None
    batch_end = args.batch[1] if args.batch else None

    run_proof(
        migrations_dir=args.migrations_dir,
        output_dir=args.output_dir,
        single=args.single,
        batch_start=batch_start,
        batch_end=batch_end,
        report_only=args.report_only,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
