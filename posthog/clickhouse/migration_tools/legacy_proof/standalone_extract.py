#!/usr/bin/env python3
"""Standalone extraction script that configures Django minimally.

This avoids full Django setup (which needs PostgreSQL) by only configuring
the settings needed for migration imports to work.

Usage:
    cd /path/to/posthog
    SECRET_KEY=x DEBUG=1 .venv/bin/python -m posthog.clickhouse.migration_tools.legacy_proof.standalone_extract [options]
"""

from __future__ import annotations

import os
import re
import ast
import sys
import json
import types
import logging
import warnings
import importlib
import importlib.util
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("legacy_proof.standalone")

_MIGRATION_PY_RE = re.compile(r"^([0-9]+)_([a-zA-Z_0-9]+)\.py$")


@dataclass
class StandaloneOp:
    index: int
    sql: str
    node_roles: list[str]
    sharded: bool
    is_alter_on_replicated_table: bool


@dataclass
class StandaloneResult:
    migration_number: int
    migration_name: str
    file_path: str
    classification: str = "exact"
    operations: list[StandaloneOp] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class _PermissiveModule(types.ModuleType):
    """A module stub that returns a no-op callable for any missing attribute.

    Used to break circular import chains during proof extraction. When
    code does ``from posthog.tasks.tasks import some_function``, the stub
    returns a no-op instead of raising ImportError.
    """

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **kw: None


def _make_permissive_stub(name: str, is_package: bool = False) -> types.ModuleType:
    """Create a permissive stub module and register it in sys.modules."""
    mod = _PermissiveModule(name)
    if is_package:
        mod.__path__ = [str(Path(name.replace(".", "/")).resolve())]
    sys.modules[name] = mod
    return mod


def _minimal_django_setup():
    """Set up Django by stubbing modules that cause circular imports.

    PostHog's import graph has deep circular dependencies:
      posthog.models → batch_exports.models → posthog.clickhouse.client
      → execute_async → posthog.tasks → posthog.models (CIRCULAR)

    We break these cycles by injecting permissive stub modules for
    ``posthog.clickhouse.client``, ``posthog.tasks``, and ``posthog.apps``
    BEFORE calling ``django.setup()``. After setup completes (models loaded),
    we re-import the real ``connection`` and ``migration_tools`` modules.
    """
    os.environ.setdefault("SECRET_KEY", "standalone-proof-key")
    os.environ.setdefault("DEBUG", "1")
    os.environ.setdefault("DATABASE_URL", "postgres://localhost:5432/posthog")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
    os.environ.setdefault("CLICKHOUSE_HOST", "localhost")
    os.environ.setdefault("CLICKHOUSE_DATABASE", "posthog")
    os.environ.setdefault("CLICKHOUSE_CLUSTER", "posthog")
    os.environ["SKIP_ASYNC_MIGRATIONS_SETUP"] = "1"
    os.environ["DJANGO_SETTINGS_MODULE"] = "posthog.settings"

    # Stub posthog.clickhouse.client and its submodules to break the
    # batch_exports → client → execute_async → tasks → models cycle.
    stub_client = _make_permissive_stub("posthog.clickhouse.client", is_package=True)
    _make_permissive_stub("posthog.clickhouse.client.execute")
    _make_permissive_stub("posthog.clickhouse.client.execute_async")

    # Stub posthog.tasks to prevent tasks → models cycle.
    _make_permissive_stub("posthog.tasks", is_package=True)
    _make_permissive_stub("posthog.tasks.tasks")

    # Stub posthog.apps to prevent module-level side effects in its ready().
    from django.apps import AppConfig

    stub_apps_mod = types.ModuleType("posthog.apps")

    class _ProofPostHogConfig(AppConfig):
        name = "posthog"
        verbose_name = "PostHog"
        default_auto_field = "django.db.models.BigAutoField"

        def ready(self):
            pass

    stub_apps_mod.PostHogConfig = _ProofPostHogConfig
    sys.modules["posthog.apps"] = stub_apps_mod

    # Now django.setup() can proceed — circular imports are broken.
    import django

    django.setup()

    # Re-import the real modules we need (now that model registry is ready).
    from posthog.clickhouse.client import connection

    stub_client.connection = connection

    from posthog.clickhouse.client import migration_tools

    stub_client.migration_tools = migration_tools


def _classify_source(source: str) -> tuple[str, list[str]]:
    """Classify a migration based on its AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return "manual-review", [f"SyntaxError: {e}"]

    has_operations = False
    has_loops = False
    has_settings_conditional = False
    imports_sql_modules = False
    is_empty_ops = False
    has_run_sql = False
    has_run_python = False

    for node in ast.walk(tree):
        # Handle both plain assignment and annotated assignment (e.g. operations: list[Never] = [])
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "operations":
                    has_operations = True
                    if isinstance(node.value, (ast.IfExp, ast.BinOp)):
                        has_settings_conditional = True
                    if isinstance(node.value, ast.List) and len(node.value.elts) == 0:
                        is_empty_ops = True
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "operations":
                has_operations = True
                if node.value is not None and isinstance(node.value, ast.List) and len(node.value.elts) == 0:
                    is_empty_ops = True

        if isinstance(node, (ast.For, ast.While)):
            has_loops = True

        if isinstance(node, ast.ImportFrom):
            if node.module and ".sql" in node.module:
                imports_sql_modules = True

        if isinstance(node, ast.Call):
            func = node.func
            # run_sql_with_exceptions(...)
            if isinstance(func, ast.Name) and func.id == "run_sql_with_exceptions":
                has_run_sql = True
            # migrations.RunPython(...)
            elif isinstance(func, ast.Attribute) and func.attr == "RunPython":
                has_run_python = True

    if not has_operations:
        return "manual-review", ["No 'operations' variable found"]
    if is_empty_ops and not has_loops:
        return "exact", ["Empty operations list (no-op migration)"]
    if has_run_python and not has_run_sql:
        return "manual-review", ["Contains RunPython operations (not SQL-based)"]
    if has_loops:
        # Loops with run_sql_with_exceptions are still deterministic
        if has_run_sql:
            return "inferred", ["Loop-based run_sql_with_exceptions calls"]
        return "manual-review", ["Contains loop(s) building operations dynamically"]
    if has_settings_conditional:
        return "manual-review", ["Operations list uses conditional expression"]
    if imports_sql_modules:
        return "inferred", ["SQL generated via imported helper functions"]
    if has_run_sql:
        return "exact", []
    return "manual-review", ["Unknown pattern"]


def _extract_node_role_str(role) -> str:
    if hasattr(role, "value"):
        return str(role.value)
    return str(role)


def extract_single(file_path: Path) -> StandaloneResult:
    """Extract operations from a single migration file."""
    match = _MIGRATION_PY_RE.match(file_path.name)
    if not match:
        return StandaloneResult(
            migration_number=0,
            migration_name=file_path.stem,
            file_path=str(file_path),
            classification="manual-review",
            error="Bad filename",
        )

    number = int(match.group(1))
    name = f"{match.group(1)}_{match.group(2)}"
    source = file_path.read_text()
    classification, source_warns = _classify_source(source)

    result = StandaloneResult(
        migration_number=number,
        migration_name=name,
        file_path=str(file_path),
        classification=classification,
        warnings=source_warns,
    )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            spec = importlib.util.spec_from_file_location(f"_proof_.{file_path.stem}", str(file_path))
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load {file_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
            finally:
                sys.modules.pop(spec.name, None)

        ops = getattr(module, "operations", None)
        if ops is None:
            result.classification = "manual-review"
            result.warnings.append("No 'operations' attribute")
            return result

        if not isinstance(ops, list):
            result.classification = "manual-review"
            result.warnings.append(f"'operations' is {type(ops).__name__}, not list")
            return result

        for i, op in enumerate(ops):
            sql = getattr(op, "_sql", None)
            node_roles = getattr(op, "_node_roles", None)
            sharded = getattr(op, "_sharded", None) or False
            is_alter = getattr(op, "_is_alter_on_replicated_table", None) or False

            if sql is None:
                result.warnings.append(f"Op {i}: no _sql (likely RunPython)")
                result.classification = "manual-review"
                # Still record the op with empty SQL so step count is preserved
                result.operations.append(
                    StandaloneOp(
                        index=i,
                        sql="-- RunPython: SQL not extractable",
                        node_roles=["all"],
                        sharded=False,
                        is_alter_on_replicated_table=False,
                    )
                )
                continue

            if callable(sql):
                try:
                    sql = sql()
                except Exception as e:
                    result.warnings.append(f"Op {i}: SQL callable failed: {e}")
                    result.classification = "manual-review"
                    continue

            role_strs = []
            if node_roles:
                for role in node_roles:
                    role_strs.append(_extract_node_role_str(role))
            else:
                role_strs = ["data"]

            result.operations.append(
                StandaloneOp(
                    index=i,
                    sql=str(sql),
                    node_roles=role_strs,
                    sharded=bool(sharded),
                    is_alter_on_replicated_table=bool(is_alter),
                )
            )

    except Exception as e:
        result.error = str(e)
        result.classification = "manual-review"
        result.warnings.append(f"Import failed: {e}")

    return result


def extract_all(migrations_dir: Path) -> list[StandaloneResult]:
    """Extract all legacy migrations."""
    files = sorted(
        [f for f in migrations_dir.iterdir() if f.is_file() and _MIGRATION_PY_RE.match(f.name)],
        key=lambda f: int(_MIGRATION_PY_RE.match(f.name).group(1)),
    )
    results = []
    for fp in files:
        logger.info("Extracting: %s", fp.name)
        results.append(extract_single(fp))
    return results


def generate_manifest_yaml(result: StandaloneResult) -> str:
    """Generate manifest YAML from extraction result."""
    import yaml

    _VALUE_TO_ROLE = {
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

    if not result.operations:
        return yaml.dump(
            {
                "description": f"[{result.classification}] {result.migration_name} (no-op)",
                "steps": [{"sql": "up.sql", "node_roles": ["ALL"], "comment": "no-op"}],
                "rollback": [{"sql": "down.sql", "node_roles": ["ALL"], "comment": "no-op"}],
            },
            default_flow_style=False,
            sort_keys=False,
        )

    use_sections = len(result.operations) > 1
    steps = []
    rollback = []

    for op in result.operations:
        sql_ref = f"up.sql#step_{op.index}" if use_sections else "up.sql"
        roles = [_VALUE_TO_ROLE.get(r, r.upper()) for r in op.node_roles]
        step: dict = {"sql": sql_ref, "node_roles": roles}
        if op.sharded:
            step["sharded"] = True
        if op.is_alter_on_replicated_table:
            step["is_alter_on_replicated_table"] = True
        steps.append(step)

        rb_ref = f"down.sql#step_{op.index}" if use_sections else "down.sql"
        rollback.append({"sql": rb_ref, "node_roles": roles, "comment": "rollback stub"})

    return yaml.dump(
        {
            "description": f"[{result.classification}] {result.migration_name}",
            "steps": steps,
            "rollback": rollback,
        },
        default_flow_style=False,
        sort_keys=False,
    )


def _templatize_sql(sql: str, db: str, cluster: str, single_shard: str) -> str:
    """Replace hardcoded settings values with Jinja2 template variables."""
    result = sql
    if db:
        result = re.sub(rf"(?<![a-zA-Z0-9_]){re.escape(db)}(?=\.)", f"{{{{ database }}}}", result)
        result = result.replace(f"'{db}'", "'{{ database }}'")
    if cluster:
        result = result.replace(f"'{cluster}'", "'{{ cluster }}'")
    if single_shard:
        result = result.replace(f"'{single_shard}'", "'{{ single_shard_cluster }}'")
    return result


def generate_up_sql(result: StandaloneResult, db: str, cluster: str, single_shard: str) -> str:
    """Generate up.sql from extraction result."""
    if not result.operations:
        return "SELECT 1; -- no-op"

    use_sections = len(result.operations) > 1
    parts = []
    for op in result.operations:
        tmpl_sql = _templatize_sql(op.sql, db, cluster, single_shard)
        if use_sections:
            parts.append(f"-- @section: step_{op.index}\n{tmpl_sql}")
        else:
            parts.append(tmpl_sql)
    return "\n\n".join(parts)


def generate_down_sql(result: StandaloneResult) -> str:
    """Generate stub down.sql."""
    if not result.operations:
        return "SELECT 1; -- no-op rollback"

    use_sections = len(result.operations) > 1
    if not use_sections:
        return "SELECT 1; -- rollback not derivable"

    parts = [f"-- @section: step_{op.index}\nSELECT 1; -- rollback not derivable" for op in result.operations]
    return "\n\n".join(parts)


def write_artifacts(results: list[StandaloneResult], output_dir: Path) -> None:
    """Write all generated artifacts to disk."""
    from django.conf import settings as django_settings

    db = getattr(django_settings, "CLICKHOUSE_DATABASE", "posthog")
    cluster = getattr(django_settings, "CLICKHOUSE_CLUSTER", "posthog")
    single_shard = getattr(django_settings, "CLICKHOUSE_SINGLE_SHARD_CLUSTER", "")

    import yaml

    output_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        d = output_dir / r.migration_name
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.yaml").write_text(generate_manifest_yaml(r))
        (d / "up.sql").write_text(generate_up_sql(r, db, cluster, single_shard))
        (d / "down.sql").write_text(generate_down_sql(r))
        (d / "proof_metadata.yaml").write_text(
            yaml.dump(
                {
                    "migration_number": r.migration_number,
                    "migration_name": r.migration_name,
                    "classification": r.classification,
                    "warnings": r.warnings,
                    "error": r.error,
                    "op_count": len(r.operations),
                },
                default_flow_style=False,
                sort_keys=False,
            )
        )


def compare_and_report(results: list[StandaloneResult], output_dir: Path) -> dict:
    """Run comparison and generate reports."""
    import yaml

    from posthog.clickhouse.migration_tools.legacy_proof.normalizer import normalize_node_roles, normalize_sql

    comparisons = []
    for r in results:
        gen_dir = output_dir / r.migration_name
        if not gen_dir.exists():
            comparisons.append(
                {
                    "number": r.migration_number,
                    "name": r.migration_name,
                    "classification": r.classification,
                    "verdict": "mismatch",
                    "note": "No generated artifact",
                }
            )
            continue

        manifest_text = (gen_dir / "manifest.yaml").read_text()
        manifest = yaml.safe_load(manifest_text)
        up_sql_text = (gen_dir / "up.sql").read_text()

        gen_steps = manifest.get("steps", [])
        legacy_op_count = len(r.operations)
        gen_step_count = len(gen_steps)

        if legacy_op_count == 0 and gen_step_count <= 1:
            if r.classification == "manual-review":
                noop_verdict = "manual_review_needed"
            elif r.classification == "inferred":
                noop_verdict = "inferred_pass"
            else:
                noop_verdict = "exact_pass"
            comparisons.append(
                {
                    "number": r.migration_number,
                    "name": r.migration_name,
                    "classification": r.classification,
                    "verdict": noop_verdict,
                    "note": "no-op",
                    "step_count": 0,
                }
            )
            continue

        step_count_match = legacy_op_count == gen_step_count

        # Parse generated SQL sections
        import re as _re

        section_re = _re.compile(r"^--\s*@section:\s*step_(\d+)\s*$", _re.MULTILINE)
        matches = list(section_re.finditer(up_sql_text))
        gen_sql_map: dict[int, str] = {}
        if matches:
            for j, m in enumerate(matches):
                idx = int(m.group(1))
                start = m.end()
                end = matches[j + 1].start() if j + 1 < len(matches) else len(up_sql_text)
                gen_sql_map[idx] = up_sql_text[start:end].strip()
        elif gen_step_count <= 1:
            gen_sql_map[0] = up_sql_text.strip()

        all_steps_pass = True
        step_details = []
        for i, op in enumerate(r.operations):
            gen_sql = gen_sql_map.get(i, "")
            norm_legacy = normalize_sql(op.sql)
            norm_gen = normalize_sql(gen_sql)

            # Handle template substitution: replace {{ var }} with the literal value
            from django.conf import settings as ds

            db = getattr(ds, "CLICKHOUSE_DATABASE", "posthog")
            cluster = getattr(ds, "CLICKHOUSE_CLUSTER", "posthog")

            single_shard = getattr(ds, "CLICKHOUSE_SINGLE_SHARD_CLUSTER", "")
            norm_gen_resolved = norm_gen
            norm_gen_resolved = norm_gen_resolved.replace("{{ database }}", db)
            norm_gen_resolved = norm_gen_resolved.replace("{{ cluster }}", cluster)
            if single_shard:
                norm_gen_resolved = norm_gen_resolved.replace("{{ single_shard_cluster }}", single_shard)

            sql_match = norm_legacy == norm_gen or norm_legacy == norm_gen_resolved

            # Also try: the legacy SQL might have ON CLUSTER that the generated doesn't
            # because the generator preserves it as-is from the source
            if not sql_match:
                # Normalize both sides more aggressively
                import re as _re2

                def _strip_extra_ws(s):
                    return _re2.sub(r"\s+", " ", s).strip()

                sql_match = _strip_extra_ws(norm_legacy) == _strip_extra_ws(norm_gen_resolved)

            gen_step = gen_steps[i] if i < gen_step_count else {}
            legacy_roles = normalize_node_roles(op.node_roles)
            gen_roles = normalize_node_roles(gen_step.get("node_roles", []))
            role_match = legacy_roles == gen_roles
            sharded_match = op.sharded == gen_step.get("sharded", False)
            alter_match = op.is_alter_on_replicated_table == gen_step.get("is_alter_on_replicated_table", False)

            step_pass = sql_match and role_match and sharded_match and alter_match
            if not step_pass:
                all_steps_pass = False

            step_details.append(
                {
                    "index": i,
                    "sql_match": sql_match,
                    "role_match": role_match,
                    "sharded_match": sharded_match,
                    "alter_match": alter_match,
                }
            )

        if r.classification == "manual-review":
            verdict = "manual_review_needed"
        elif all_steps_pass and step_count_match:
            verdict = "exact_pass" if r.classification == "exact" else "inferred_pass"
        else:
            verdict = "mismatch"

        comparisons.append(
            {
                "number": r.migration_number,
                "name": r.migration_name,
                "classification": r.classification,
                "verdict": verdict,
                "step_count_match": step_count_match,
                "steps": step_details,
                "warnings": r.warnings,
            }
        )

    # Summary
    verdicts = Counter(c["verdict"] for c in comparisons)
    classifications = Counter(c["classification"] for c in comparisons)
    passing = sum(1 for c in comparisons if "pass" in c["verdict"])
    total = len(comparisons)
    pass_rate = passing / total if total > 0 else 0.0

    report = {
        "total": total,
        "pass_rate": f"{pass_rate:.1%}",
        "by_verdict": dict(verdicts),
        "by_classification": dict(classifications),
        "migrations": comparisons,
    }

    # Write reports
    report_dir = output_dir / "proof_report"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # Text summary
    lines = [
        "=" * 80,
        "CLICKHOUSE LEGACY-TO-DECLARATIVE PROOF REPORT",
        "=" * 80,
        "",
        f"Total: {total}",
        f"Pass rate: {pass_rate:.1%}",
        "",
        "By verdict:",
    ]
    for v, count in sorted(verdicts.items()):
        lines.append(f"  {v}: {count}")
    lines.append("")
    lines.append("By classification:")
    for c, count in sorted(classifications.items()):
        lines.append(f"  {c}: {count}")

    # Mismatches
    mismatches = [c for c in comparisons if c["verdict"] == "mismatch"]
    if mismatches:
        lines.append(f"\nMISMATCHES ({len(mismatches)}):")
        for m in mismatches:
            lines.append(f"  {m['name']} — {m.get('note', '')}")
            for s in m.get("steps", []):
                if not all(s.get(k, True) for k in ["sql_match", "role_match", "sharded_match", "alter_match"]):
                    lines.append(
                        f"    step {s['index']}: sql={s['sql_match']} role={s['role_match']} sharded={s['sharded_match']} alter={s['alter_match']}"
                    )

    # Summary table
    lines.append(f"\n{'#':>4}  {'Name':<50}  {'Class':<15}  {'Verdict':<20}")
    lines.append("-" * 95)
    for c in comparisons:
        lines.append(f"{c['number']:>4}  {c['name']:<50}  {c['classification']:<15}  {c['verdict']:<20}")

    (report_dir / "report.txt").write_text("\n".join(lines))

    return report


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Standalone legacy-to-declarative proof")
    parser.add_argument("--migrations-dir", type=Path, default=Path("posthog/clickhouse/migrations"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/ch_migrate_proof/generated"))
    parser.add_argument("--single", type=int, default=None)
    parser.add_argument("--batch", nargs=2, type=int, default=None, metavar=("START", "END"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    logger.info("Setting up Django (minimal)...")
    _minimal_django_setup()
    logger.info("Django ready")

    mdir = args.migrations_dir
    if args.single is not None:
        files = [
            f
            for f in sorted(mdir.iterdir())
            if f.is_file()
            and _MIGRATION_PY_RE.match(f.name)
            and int(_MIGRATION_PY_RE.match(f.name).group(1)) == args.single
        ]
        results = [extract_single(f) for f in files]
    elif args.batch:
        files = [
            f
            for f in sorted(mdir.iterdir())
            if f.is_file()
            and _MIGRATION_PY_RE.match(f.name)
            and args.batch[0] <= int(_MIGRATION_PY_RE.match(f.name).group(1)) <= args.batch[1]
        ]
        results = [extract_single(f) for f in files]
    else:
        results = extract_all(mdir)

    logger.info("Extracted %d migrations", len(results))

    output_dir = args.output_dir
    logger.info("Writing artifacts to %s", output_dir)
    write_artifacts(results, output_dir)

    logger.info("Comparing and generating report...")
    compare_and_report(results, output_dir)


if __name__ == "__main__":
    main()
