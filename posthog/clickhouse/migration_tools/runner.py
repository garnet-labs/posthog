"""Step execution engine + legacy migration support."""

from __future__ import annotations

import os
import logging
import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from posthog.clickhouse.migration_tools.manifest import ROLE_MAP, ManifestStep

if TYPE_CHECKING:
    from posthog.clickhouse.cluster import ClickhouseCluster

logger = logging.getLogger("migrations")

# Legacy migrations live here
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _map_node_roles(manifest_roles: list[str]) -> list:
    from posthog.clickhouse.client.connection import NodeRole

    result = []
    for role in manifest_roles:
        role_value = ROLE_MAP.get(role)
        if role_value is None:
            raise ValueError(f"Unknown node role '{role}'. Valid roles: {sorted(ROLE_MAP.keys())}")
        result.append(NodeRole(role_value))
    return result


def execute_migration_step(
    cluster: ClickhouseCluster,
    step: ManifestStep,
    rendered_sql: str,
) -> dict[Any, Any]:
    """Routing: sharded+alter_replicated -> one_host_per_shard, alter_replicated -> any_host, else -> all hosts."""
    from posthog.clickhouse.cluster import Query

    query = Query(rendered_sql)
    node_roles = _map_node_roles(step.node_roles)

    if step.sharded and step.is_alter_on_replicated_table:
        futures_map = cluster.map_one_host_per_shard(query)
        return futures_map.result()
    elif step.is_alter_on_replicated_table:
        future = cluster.any_host_by_roles(query, node_roles=node_roles)
        result = future.result()
        return {"single_host": result}
    else:
        futures_map = cluster.map_hosts_by_roles(query, node_roles=node_roles)
        return futures_map.result()


def discover_migrations() -> list[str]:
    if not MIGRATIONS_DIR.exists():
        return []

    migrations = []
    for entry in sorted(os.listdir(MIGRATIONS_DIR)):
        # Match NNNN_name.py or NNNN_name/ (directory migrations)
        if entry.startswith("0") and not entry.startswith("__"):
            name = entry.removesuffix(".py")
            # Only include .py files and directories with __init__.py
            entry_path = MIGRATIONS_DIR / entry
            if entry_path.is_file() and entry.endswith(".py"):
                migrations.append(name)
            elif entry_path.is_dir() and (entry_path / "__init__.py").exists():
                migrations.append(name)

    return migrations


def get_pending_migrations() -> list[str]:
    all_migrations = discover_migrations()
    if not all_migrations:
        return []

    try:
        from posthog.clickhouse.client.migration_tools import get_migrations_cluster

        cluster = get_migrations_cluster()
        client = cluster.any_host(lambda c: c).result()

        rows = client.execute(
            "SELECT name FROM system.tables WHERE database = 'default' AND name = 'clickhouseorm_migrations'"
        )
        if not rows:
            return all_migrations  # no tracking table = everything is pending

        applied_rows = client.execute("SELECT package_name FROM default.clickhouseorm_migrations")
        applied = {row[0] for row in applied_rows}

        return [m for m in all_migrations if m not in applied]
    except Exception as exc:
        logger.warning("Could not check applied migrations, assuming all pending: %s", exc)
        return all_migrations


def check_active_mutations(client: Any, table: str, database: str = "posthog") -> list[dict[str, Any]]:
    rows = client.execute(
        "SELECT mutation_id, command, create_time, is_done "
        "FROM system.mutations "
        "WHERE database = %(database)s AND table = %(table)s AND is_done = 0",
        {"database": database, "table": table},
    )
    return [{"mutation_id": r[0], "command": r[1], "create_time": r[2], "is_done": r[3]} for r in rows]


def _run_migration_ops(migration_module_path: str, ops_attr: str) -> None:
    """Shared logic for running migration operations (up or down)."""
    module = importlib.import_module(migration_module_path)
    ops = getattr(module, ops_attr, [])

    if not ops:
        if ops_attr == "rollback_operations":
            raise ValueError(f"Migration {migration_module_path} has no rollback_operations")
        return

    from posthog.clickhouse.client.migration_tools import get_migrations_cluster

    cluster = get_migrations_cluster()

    for op in ops:
        if hasattr(op, "sql"):
            from posthog.clickhouse.cluster import Query

            cluster.map_all_hosts(Query(op.sql)).result()
        elif hasattr(op, "fn"):
            client = cluster.any_host(lambda c: c).result()
            op.fn(client)
        else:
            logger.warning("Skipping migration operation with no 'sql' or 'fn' attribute: %s", type(op).__name__)


def run_migration_up(migration_name: str) -> None:
    _run_migration_ops(f"posthog.clickhouse.migrations.{migration_name}", "operations")


def run_migration_down(migration_number: int) -> None:
    migrations = discover_migrations()
    target = next((m for m in migrations if m.startswith(f"{migration_number:04d}_")), None)

    if target is None:
        raise ValueError(f"Migration {migration_number} not found")

    _run_migration_ops(f"posthog.clickhouse.migrations.{target}", "rollback_operations")
