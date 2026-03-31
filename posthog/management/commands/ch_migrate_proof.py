# ruff: noqa: T201 allow print statements
"""Management command for the legacy-to-declarative migration proof system.

Provides subcommands for:
- extract: Extract and classify the legacy migration corpus
- generate: Generate declarative proof artifacts
- compare: Compare legacy vs generated artifacts
- report: Generate proof reports
- run: Full proof pipeline (extract + generate + compare + report)
- replay: Differential replay harness (requires live ClickHouse)
- checkpoints: List/run checkpoint-based upgrade proof
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from django.core.management.base import BaseCommand

logger = logging.getLogger("legacy_proof")

# Default paths
DEFAULT_MIGRATIONS_DIR = Path("posthog/clickhouse/migrations")
DEFAULT_OUTPUT_DIR = Path("tmp/ch_migrate_proof")

# Checkpoint eras: represent major transitions in the migration history.
# Each checkpoint is a migration number where the schema state represents
# a meaningful historical snapshot for upgrade replay testing.
CHECKPOINT_ERAS = {
    "bootstrap": {
        "migration": 1,
        "description": "Initial schema: events, persons, sessions",
    },
    "distributed": {
        "migration": 35,
        "description": "Coordinator and distributed table introduction",
    },
    "ingestion_layer": {
        "migration": 96,
        "description": "Ingestion layer separation (sharded/non-sharded)",
    },
    "sessions_v2": {
        "migration": 100,
        "description": "Sessions v2 raw_sessions infrastructure",
    },
    "replay_expansion": {
        "migration": 136,
        "description": "Session replay retention and expansion",
    },
    "logs_era": {
        "migration": 200,
        "description": "Logs pipeline migration era",
    },
    "pre_declarative": {
        "migration": 223,
        "description": "Last legacy migration before 0224 bootstrap",
    },
}


class Command(BaseCommand):
    help = "Legacy-to-declarative ClickHouse migration proof system"

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="subcommand")

        # --- run (full pipeline) ---
        run_p = subparsers.add_parser("run", help="Run the full proof pipeline")
        run_p.add_argument("--single", type=int, default=None, help="Single migration number")
        run_p.add_argument("--batch", nargs=2, type=int, metavar=("START", "END"))
        run_p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        run_p.add_argument("--verbose", action="store_true")

        # --- report ---
        report_p = subparsers.add_parser("report", help="Print the latest proof report")
        report_p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        report_p.add_argument("--json", action="store_true", help="Output JSON instead of text")

        # --- checkpoints ---
        cp_p = subparsers.add_parser("checkpoints", help="List or run checkpoint-based proof")
        cp_p.add_argument("--list", action="store_true", help="List checkpoint eras")
        cp_p.add_argument("--run", type=str, default=None, help="Run specific checkpoint era")
        cp_p.add_argument("--run-all", action="store_true", help="Run all checkpoint eras")
        cp_p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)

        # --- classify ---
        cls_p = subparsers.add_parser("classify", help="Show classification summary")
        cls_p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)

    def handle(self, *args, **options):
        subcmd = options.get("subcommand")
        if subcmd == "run":
            self._handle_run(options)
        elif subcmd == "report":
            self._handle_report(options)
        elif subcmd == "checkpoints":
            self._handle_checkpoints(options)
        elif subcmd == "classify":
            self._handle_classify(options)
        else:
            self.stderr.write("Usage: ch_migrate_proof <run|report|checkpoints|classify>")

    def _handle_run(self, options):
        """Run the full proof pipeline."""
        import warnings

        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import (
            compare_and_report,
            extract_all,
            extract_single,
            write_artifacts,
        )

        mdir = DEFAULT_MIGRATIONS_DIR
        output_dir = options["output_dir"]
        generated_dir = output_dir / "generated"

        import re

        _RE = re.compile(r"^([0-9]+)_([a-zA-Z_0-9]+)\.py$")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            if options.get("single") is not None:
                files = [
                    f
                    for f in sorted(mdir.iterdir())
                    if f.is_file()
                    and _RE.match(f.name)
                    and int(_RE.match(f.name).group(1)) == options["single"]
                ]
                results = [extract_single(f) for f in files]
                mode = f"single migration {options['single']:04d}"
            elif options.get("batch"):
                start, end = options["batch"]
                files = [
                    f
                    for f in sorted(mdir.iterdir())
                    if f.is_file() and _RE.match(f.name) and start <= int(_RE.match(f.name).group(1)) <= end
                ]
                results = [extract_single(f) for f in files]
                mode = f"batch {start:04d}-{end:04d}"
            else:
                results = extract_all(mdir)
                mode = "full corpus"

        print(f"Extracted {len(results)} migrations ({mode})")

        write_artifacts(results, generated_dir)
        print(f"Generated artifacts in {generated_dir}")

        report = compare_and_report(results, generated_dir)
        print(f"\nTotal: {report['total']}")
        print(f"Pass rate: {report['pass_rate']}")
        print(f"By verdict: {report['by_verdict']}")
        print(f"By classification: {report['by_classification']}")

        # Print mismatches if any
        mismatches = [m for m in report["migrations"] if m["verdict"] == "mismatch"]
        if mismatches:
            print(f"\nMISMATCHES ({len(mismatches)}):")
            for m in mismatches:
                print(f"  {m['name']}: {m.get('note', '')}")

    def _handle_report(self, options):
        """Print the latest proof report."""
        output_dir = options["output_dir"]
        report_dir = output_dir / "generated" / "proof_report"

        if options.get("json"):
            report_json = report_dir / "report.json"
            if report_json.exists():
                print(report_json.read_text())
            else:
                self.stderr.write(f"No report found at {report_json}. Run 'ch_migrate_proof run' first.")
        else:
            report_txt = report_dir / "report.txt"
            if report_txt.exists():
                print(report_txt.read_text())
            else:
                self.stderr.write(f"No report found at {report_txt}. Run 'ch_migrate_proof run' first.")

    def _handle_checkpoints(self, options):
        """List or run checkpoint-based upgrade proof."""
        if options.get("list"):
            print("Checkpoint eras for upgrade replay:")
            print(f"{'Era':<20} {'Migration':>10} {'Description'}")
            print("-" * 70)
            for era, info in CHECKPOINT_ERAS.items():
                print(f"{era:<20} {info['migration']:>10} {info['description']}")
            return

        if options.get("run"):
            era = options["run"]
            if era not in CHECKPOINT_ERAS:
                self.stderr.write(f"Unknown era '{era}'. Use --list to see available eras.")
                return
            self._run_checkpoint(era, options)
            return

        if options.get("run_all"):
            for era in CHECKPOINT_ERAS:
                print(f"\n{'=' * 60}")
                print(f"CHECKPOINT ERA: {era}")
                print(f"{'=' * 60}")
                self._run_checkpoint(era, options)
            return

        print("Usage: ch_migrate_proof checkpoints <--list|--run ERA|--run-all>")

    def _run_checkpoint(self, era: str, options):
        """Run proof for a specific checkpoint era (upgrade replay simulation).

        This runs the proof pipeline for migrations AFTER the checkpoint,
        simulating an upgrade from that historical state.
        """
        import warnings

        from posthog.clickhouse.migration_tools.legacy_proof.standalone_extract import (
            compare_and_report,
            extract_single,
            write_artifacts,
        )

        info = CHECKPOINT_ERAS[era]
        start_migration = info["migration"]
        output_dir = options["output_dir"] / f"checkpoint_{era}"
        generated_dir = output_dir / "generated"

        import re

        _RE = re.compile(r"^([0-9]+)_([a-zA-Z_0-9]+)\.py$")
        mdir = DEFAULT_MIGRATIONS_DIR

        files = [
            f
            for f in sorted(mdir.iterdir())
            if f.is_file() and _RE.match(f.name) and int(_RE.match(f.name).group(1)) > start_migration
        ]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            results = [extract_single(f) for f in files]

        print(f"Checkpoint '{era}': migrations {start_migration + 1}+ ({len(results)} migrations)")
        write_artifacts(results, generated_dir)
        report = compare_and_report(results, generated_dir)

        print(f"  Pass rate: {report['pass_rate']}")
        print(f"  By verdict: {report['by_verdict']}")

        # Save checkpoint report
        report_file = output_dir / "checkpoint_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(
            json.dumps(
                {
                    "era": era,
                    "start_migration": start_migration,
                    "description": info["description"],
                    **{k: v for k, v in report.items() if k != "migrations"},
                },
                indent=2,
            )
        )
        print(f"  Report: {report_file}")

    def _handle_classify(self, options):
        """Show classification summary from the latest report."""
        output_dir = options["output_dir"]
        report_json = output_dir / "generated" / "proof_report" / "report.json"
        if not report_json.exists():
            self.stderr.write(f"No report found. Run 'ch_migrate_proof run' first.")
            return

        report = json.loads(report_json.read_text())

        # Group by classification
        from collections import defaultdict

        by_class: dict[str, list] = defaultdict(list)
        for m in report["migrations"]:
            by_class[m["classification"]].append(m)

        for cls in ["exact", "inferred", "manual-review"]:
            migrations = by_class.get(cls, [])
            print(f"\n{cls.upper()} ({len(migrations)}):")
            for m in migrations:
                verdict = m["verdict"]
                warns = ", ".join(m.get("warnings", [])[:1])
                print(f"  {m['name']:<50} {verdict:<20} {warns}")
