"""Extract operations metadata from legacy .py ClickHouse migrations.

This module evaluates legacy migration files and captures the metadata
attached by ``run_sql_with_exceptions`` (``_sql``, ``_node_roles``,
``_sharded``, ``_is_alter_on_replicated_table``).

Because many migrations call SQL-builder helper functions, extraction
requires a Django-configured environment so that the imports succeed.
"""

from __future__ import annotations

import re
import ast
import sys
import logging
import warnings
import importlib
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("legacy_proof.extractor")

# Match legacy migration filenames: 0001_initial.py
_MIGRATION_PY_RE = re.compile(r"^([0-9]+)_([a-zA-Z_0-9]+)\.py$")


@dataclass
class ExtractedOperation:
    """Metadata for a single ``run_sql_with_exceptions`` call."""

    index: int
    sql: str
    node_roles: list[str]  # NodeRole enum values as strings
    sharded: bool
    is_alter_on_replicated_table: bool


@dataclass
class ExtractionResult:
    """Result of extracting operations from one legacy migration."""

    migration_number: int
    migration_name: str
    file_path: str
    operations: list[ExtractedOperation] = field(default_factory=list)
    classification: str = "exact"  # exact | inferred | manual-review
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def _classify_source(source: str, file_path: str) -> tuple[str, list[str]]:
    """Classify a migration source file before evaluation.

    Returns (classification, warnings_list).
    """
    warns: list[str] = []

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return "manual-review", [f"SyntaxError: {e}"]

    has_operations = False
    has_loops = False
    has_sql_helpers = False
    has_settings_conditional = False
    imports_sql_modules = False
    is_empty_ops = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "operations":
                    has_operations = True
                    # Check for conditional operations (ternary / BinOp)
                    if isinstance(node.value, ast.IfExp):
                        has_settings_conditional = True
                    if isinstance(node.value, ast.BinOp):
                        # e.g. operations = [...] if cond else []
                        has_settings_conditional = True
                    # Check for empty list
                    if isinstance(node.value, ast.List) and len(node.value.elts) == 0:
                        is_empty_ops = True

        if isinstance(node, (ast.For, ast.While)):
            has_loops = True

        if isinstance(node, ast.If):
            # If inside function or at module level with operations-affecting logic
            pass

        if isinstance(node, ast.ImportFrom):
            if node.module and ".sql" in node.module:
                imports_sql_modules = True
            for alias in node.names or []:
                name = alias.name
                if name.endswith("_SQL") or name.endswith("_sql"):
                    has_sql_helpers = True

    if not has_operations:
        return "manual-review", ["No 'operations' variable found"]

    if is_empty_ops:
        return "exact", ["Empty operations list (no-op migration)"]

    if has_loops:
        warns.append("Contains loop(s) building operations dynamically")
        return "manual-review", warns

    if has_settings_conditional:
        warns.append("Operations list uses conditional expression (settings/deployment check)")
        return "manual-review", warns

    if has_sql_helpers or imports_sql_modules:
        warns.append("SQL generated via imported helper functions")
        return "inferred", warns

    return "exact", warns


def _extract_node_role_str(role: Any) -> str:
    """Convert a NodeRole enum value to its string representation."""
    return str(role.value) if hasattr(role, "value") else str(role)


def extract_migration(file_path: Path) -> ExtractionResult:
    """Extract operations from a single legacy migration file.

    Requires Django to be configured (``django.setup()`` must have been called).
    """
    match = _MIGRATION_PY_RE.match(file_path.name)
    if not match:
        return ExtractionResult(
            migration_number=0,
            migration_name=file_path.stem,
            file_path=str(file_path),
            classification="manual-review",
            error=f"Filename does not match migration pattern: {file_path.name}",
        )

    number = int(match.group(1))
    name = f"{match.group(1)}_{match.group(2)}"

    source = file_path.read_text()
    classification, source_warns = _classify_source(source, str(file_path))

    result = ExtractionResult(
        migration_number=number,
        migration_name=name,
        file_path=str(file_path),
        classification=classification,
        warnings=source_warns,
    )

    # Try to actually evaluate the module to get real SQL
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            module = _import_migration_module(file_path)

        ops = getattr(module, "operations", None)
        if ops is None:
            result.classification = "manual-review"
            result.warnings.append("Module has no 'operations' attribute after import")
            return result

        if not isinstance(ops, list):
            result.classification = "manual-review"
            result.warnings.append(f"'operations' is not a list: {type(ops).__name__}")
            return result

        for i, op in enumerate(ops):
            sql = getattr(op, "_sql", None)
            node_roles = getattr(op, "_node_roles", None)
            sharded = getattr(op, "_sharded", None) or False
            is_alter = getattr(op, "_is_alter_on_replicated_table", None) or False

            if sql is None:
                result.warnings.append(f"Operation {i} has no _sql attribute")
                if result.classification == "exact":
                    result.classification = "inferred"
                continue

            # Resolve SQL if it's callable
            if callable(sql):
                try:
                    sql = sql()
                except Exception as e:
                    result.warnings.append(f"Operation {i}: SQL callable failed: {e}")
                    result.classification = "manual-review"
                    continue

            # Convert node_roles
            role_strs: list[str] = []
            if node_roles:
                for role in node_roles:
                    role_strs.append(_extract_node_role_str(role))
            else:
                role_strs = ["data"]  # default

            result.operations.append(
                ExtractedOperation(
                    index=i,
                    sql=str(sql),
                    node_roles=role_strs,
                    sharded=bool(sharded),
                    is_alter_on_replicated_table=bool(is_alter),
                )
            )

    except Exception as e:
        result.error = f"Import/evaluation failed: {e}"
        if result.classification != "manual-review":
            result.classification = "manual-review"
        result.warnings.append(f"Module evaluation failed: {e}")

    return result


def _import_migration_module(file_path: Path) -> Any:
    """Import a migration .py file as a module."""
    module_name = f"_legacy_proof_eval_.{file_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def extract_all_migrations(
    migrations_dir: Path,
) -> list[ExtractionResult]:
    """Extract operations from all legacy .py migrations in a directory."""
    results: list[ExtractionResult] = []

    files = sorted(
        [f for f in migrations_dir.iterdir() if f.is_file() and _MIGRATION_PY_RE.match(f.name)],
        key=lambda f: int(_MIGRATION_PY_RE.match(f.name).group(1)),  # type: ignore
    )

    for file_path in files:
        logger.info("Extracting: %s", file_path.name)
        result = extract_migration(file_path)
        results.append(result)

    return results
