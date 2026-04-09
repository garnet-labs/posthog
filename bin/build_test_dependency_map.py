#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "grimp==3.13",
# ]
# ///
"""
Build a reverse dependency map: source file -> test files that import it.

Uses grimp to build the full import graph, identifies test modules, computes
their transitive dependencies, and inverts the result. The output is used by
find_affected_tests.py to determine which tests to run for a given set of
changed files.

Usage:
    # Generate the map (writes to .test_dependency_map.json)
    python bin/build_test_dependency_map.py

    # Write to a custom path
    python bin/build_test_dependency_map.py --output /tmp/map.json

    # Print stats without writing
    python bin/build_test_dependency_map.py --dry-run
"""

import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import grimp

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

LOCAL_PACKAGES = ("posthog", "ee", "products", "common")
DEFAULT_OUTPUT = REPO_ROOT / ".test_dependency_map.json"

# Source files affecting more tests than this are excluded from the map.
# Changing them effectively requires a full run anyway, and including them
# bloats the file from ~2MB to ~55MB. find_affected_tests.py treats
# excluded files as "force full run" via the safety fallback.
MAX_FANOUT = 100

# Patterns that identify test files
TEST_FILE_RE = re.compile(r"(^|/)test_[^/]*\.py$")
TEST_DIR_RE = re.compile(r"(^|/)tests?/")
EVAL_FILE_RE = re.compile(r"(^|/)eval_[^/]*\.py$")


def is_test_module(module: str, file_path: str | None) -> bool:
    if file_path is None:
        return False
    return bool(TEST_FILE_RE.search(file_path) or EVAL_FILE_RE.search(file_path))


def module_to_file(module: str) -> str | None:
    path = module.replace(".", "/")
    if os.path.isfile(f"{path}.py"):
        return f"{path}.py"
    if os.path.isfile(f"{path}/__init__.py"):
        return f"{path}/__init__.py"
    return None


def get_current_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()[:12]
    except Exception:
        return "unknown"


def build_map(graph: grimp.ImportGraph) -> dict[str, list[str]]:
    all_modules = graph.modules

    # Classify modules as test or source
    test_modules: set[str] = set()
    module_files: dict[str, str] = {}

    for module in all_modules:
        file_path = module_to_file(module)
        if file_path:
            module_files[module] = file_path
            if is_test_module(module, file_path):
                test_modules.add(module)

    sys.stderr.write(f"Found {len(test_modules)} test modules, {len(module_files)} total modules\n")

    # For each test module, find its upstream (transitive) dependencies
    # Then invert: source_file -> [test_files]
    reverse_map: dict[str, set[str]] = defaultdict(set)

    processed = 0
    for test_module in sorted(test_modules):
        test_file = module_files[test_module]

        try:
            upstream = graph.find_upstream_modules(test_module)
        except Exception as e:
            sys.stderr.write(f"  Warning: could not resolve deps for {test_module}: {e}\n")
            continue

        for dep_module in upstream:
            if dep_module in module_files and dep_module not in test_modules:
                dep_file = module_files[dep_module]
                reverse_map[dep_file].add(test_file)

        processed += 1
        if processed % 100 == 0:
            sys.stderr.write(f"  Processed {processed}/{len(test_modules)} test modules...\n")

    # Exclude high-fan-out entries (core/shared modules that affect too many tests).
    # Changing these files practically requires a full test run anyway, and including
    # them bloats the map file significantly.
    excluded = {k for k, v in reverse_map.items() if len(v) > MAX_FANOUT}
    # Also drop entries where a test file only references itself — that's implicit
    self_only = {k for k, v in reverse_map.items() if v == {k}}
    filtered_map = {k: v for k, v in reverse_map.items() if k not in excluded and k not in self_only}

    sys.stderr.write(
        f"Map covers {len(filtered_map)} source files "
        f"(excluded {len(excluded)} high-fan-out files with >{MAX_FANOUT} tests)\n"
    )

    # Convert sets to sorted lists for JSON serialization
    return {k: sorted(v) for k, v in sorted(filtered_map.items())}


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build reverse dependency map: source file -> test files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output file path (default: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats without writing the map file",
    )
    args = parser.parse_args()

    start = time.monotonic()
    sys.stderr.write(f"Building import graph for packages: {', '.join(LOCAL_PACKAGES)}...\n")

    try:
        graph = grimp.build_graph(*LOCAL_PACKAGES)
    except Exception as e:
        sys.stderr.write(f"Error building import graph: {e}\n")
        sys.exit(1)

    elapsed_graph = time.monotonic() - start
    sys.stderr.write(f"Import graph built in {elapsed_graph:.1f}s ({len(graph.modules)} modules)\n")

    reverse_map = build_map(graph)
    elapsed_total = time.monotonic() - start

    # Compute stats
    all_test_files = set()
    for tests in reverse_map.values():
        all_test_files.update(tests)

    # Find fan-out: source files that affect the most tests
    top_fanout = sorted(reverse_map.items(), key=lambda x: len(x[1]), reverse=True)[:10]

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": get_current_commit(),
        "test_file_count": len(all_test_files),
        "source_file_count": len(reverse_map),
        "build_time_seconds": round(elapsed_total, 1),
    }

    sys.stderr.write(f"\nStats:\n")
    sys.stderr.write(f"  Source files mapped: {meta['source_file_count']}\n")
    sys.stderr.write(f"  Test files covered:  {meta['test_file_count']}\n")
    sys.stderr.write(f"  Build time:          {meta['build_time_seconds']}s\n")
    sys.stderr.write(f"\n  Top fan-out (source files affecting most tests):\n")
    for source, tests in top_fanout:
        sys.stderr.write(f"    {source}: {len(tests)} tests\n")

    if args.dry_run:
        sys.stderr.write("\nDry run — not writing output file.\n")
        sys.stdout.write(json.dumps(meta, indent=2) + "\n")
        return

    output = {"_meta": meta, **reverse_map}
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    sys.stderr.write(f"\nWrote {args.output.relative_to(REPO_ROOT)}\n")


if __name__ == "__main__":
    main()
