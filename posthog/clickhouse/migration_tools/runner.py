from __future__ import annotations

import re
import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from posthog.clickhouse.migration_tools.manifest import ROLE_MAP, ManifestStep, MigrationManifest
from posthog.clickhouse.migration_tools.tracking import (
    MIGRATION_COMPLETE_STEP,
    TRACKING_TABLE_NAME,
    StepRecord,
    get_applied_migrations,
    get_step_results,
    record_step,
)

if TYPE_CHECKING:
    from posthog.clickhouse.client.connection import NodeRole
    from posthog.clickhouse.cluster import ClickhouseCluster

logger = logging.getLogger("migrations")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_MIGRATION_PY_RE = re.compile(r"^([0-9]+)_([a-zA-Z_0-9]+)\.py$")
_MIGRATION_DIR_RE = re.compile(r"^([0-9]+)_([a-zA-Z_0-9]+)$")
_SAFE_TABLE_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def _map_node_roles(manifest_roles: list[str]) -> list[NodeRole]:
    from posthog.clickhouse.client.connection import NodeRole

    result = []
    for role in manifest_roles:
        role_value = ROLE_MAP.get(role)
        if role_value is None:
            raise ValueError(f"Unknown node role '{role}'. Valid roles: {sorted(ROLE_MAP.keys())}")
        result.append(NodeRole(role_value))
    return result


def _resolve_step_clusters(step: ManifestStep, manifest: MigrationManifest) -> list[str] | None:
    if step.clusters is not None:
        return step.clusters
    return manifest.clusters


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[dict[str, Any]]:
    migrations: list[dict[str, Any]] = []

    for entry in migrations_dir.iterdir():
        if entry.name.startswith("_"):
            continue

        if entry.is_file():
            match = _MIGRATION_PY_RE.match(entry.name)
            if match:
                number = int(match.group(1))
                name = f"{match.group(1)}_{match.group(2)}"
                migrations.append(
                    {
                        "number": number,
                        "name": name,
                        "style": "py",
                        "path": entry,
                    }
                )
        elif entry.is_dir():
            match = _MIGRATION_DIR_RE.match(entry.name)
            if match and (entry / "manifest.yaml").exists():
                number = int(match.group(1))
                name = f"{match.group(1)}_{match.group(2)}"
                migrations.append(
                    {
                        "number": number,
                        "name": name,
                        "style": "new",
                        "path": entry,
                    }
                )

    migrations.sort(key=lambda m: m["number"])
    return migrations


def is_new_style(migration_dir: Path) -> bool:
    return migration_dir.is_dir() and (migration_dir / "manifest.yaml").exists()


def get_pending_migrations(
    client: Any,
    database: str,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> list[dict[str, Any]]:
    all_migrations = discover_migrations(migrations_dir)
    try:
        applied = get_applied_migrations(client, database)
    except Exception:
        # Tracking table may not exist yet (fresh cluster before bootstrap).
        # Treat all migrations as pending so bootstrap can run first.
        applied = []

    applied_numbers: set[int] = {row["migration_number"] for row in applied}

    return [m for m in all_migrations if m["number"] not in applied_numbers]


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


def _should_execute_step(
    step: ManifestStep,
    manifest: MigrationManifest,
    current_cluster: str | None,
) -> bool:
    if current_cluster is None:
        return True
    effective = _resolve_step_clusters(step, manifest)
    if effective is None:
        return True
    return current_cluster in effective


def run_migration_up(
    cluster: ClickhouseCluster,
    migration: Any,
    database: str,
    migration_number: int,
    migration_name: str,
    current_cluster: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Returns True if all steps succeeded. On partial failure: halts, tracking table shows which hosts succeeded."""
    steps = migration.get_steps()
    manifest: MigrationManifest = getattr(migration, "manifest", None) or MigrationManifest(
        description="", steps=[], rollback=[]
    )

    # Resolve tracking cluster once for all recording calls.
    tracking_cluster: Any = None
    prior_results: dict[tuple[int, str], bool] = {}
    if not dry_run:
        try:
            tracking_cluster = _get_tracking_cluster()

            def _load_results(client: Any) -> dict[tuple[int, str], bool]:
                return get_step_results(client, database, migration_number)

            result = tracking_cluster.any_host(_load_results).result()
            if isinstance(result, dict):
                prior_results = result
        except Exception:
            logger.debug("Could not load prior step results for migration %s — running all steps", migration_name)

    for step_index, (step, rendered_sql) in enumerate(steps):
        if not _should_execute_step(step, manifest, current_cluster):
            logger.info(
                "Migration %s step %d skipped (cluster=%s not targeted)",
                migration_name,
                step_index,
                current_cluster,
            )
            continue

        # Per-host retry: check if all hosts already succeeded for this step.
        if prior_results:
            step_hosts = {host for (si, host), ok in prior_results.items() if si == step_index and ok}
            if step_hosts:
                logger.info(
                    "Migration %s step %d: hosts already recorded as applied (will skip re-recording): %s",
                    migration_name,
                    step_index,
                    sorted(step_hosts),
                )

        checksum = compute_checksum(rendered_sql)

        try:
            host_results = execute_migration_step(cluster, step, rendered_sql)
        except Exception as exc:
            logger.exception(
                "Migration %s step %d failed: %s",
                migration_name,
                step_index,
                exc,
            )
            if not dry_run:
                _record_for_tracking(
                    record=StepRecord(
                        migration_number=migration_number,
                        migration_name=migration_name,
                        step_index=step_index,
                        host="unknown",
                        node_role=",".join(step.node_roles),
                        direction="up",
                        checksum=checksum,
                        success=False,
                    ),
                    database=database,
                    _tracking_cluster=tracking_cluster,
                )
            return False

        if not dry_run:
            for host_key in host_results:
                host_str = str(host_key)
                # Skip recording for hosts that already have a success record.
                if prior_results.get((step_index, host_str)):
                    continue
                _record_for_tracking(
                    record=StepRecord(
                        migration_number=migration_number,
                        migration_name=migration_name,
                        step_index=step_index,
                        host=host_str,
                        node_role=",".join(step.node_roles),
                        direction="up",
                        checksum=checksum,
                        success=True,
                    ),
                    database=database,
                    _tracking_cluster=tracking_cluster,
                )

    if not dry_run:
        _record_for_tracking(
            record=StepRecord(
                migration_number=migration_number,
                migration_name=migration_name,
                step_index=MIGRATION_COMPLETE_STEP,
                host="*",
                node_role="*",
                direction="up",
                checksum="complete",
                success=True,
            ),
            database=database,
            _tracking_cluster=tracking_cluster,
        )

    return True


def _get_tracking_cluster() -> Any:
    from posthog.clickhouse.client.migration_tools import get_migrations_cluster

    return get_migrations_cluster()


def _record_for_tracking(
    *,
    record: StepRecord,
    database: str,
    _tracking_cluster: Any = None,
) -> None:
    tc = _tracking_cluster if _tracking_cluster is not None else _get_tracking_cluster()

    def _do_record(client: Any) -> None:
        record_step(client=client, record=record, database=database)

    tc.any_host(_do_record).result()


def _drops_tracking_table(sql: str, database: str) -> bool:
    pattern = (
        rf"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?"
        rf"(?:`?{re.escape(database)}`?\.)?`?{TRACKING_TABLE_NAME}`?"
    )
    return re.search(pattern, sql, flags=re.IGNORECASE) is not None


def run_migration_down(
    cluster: ClickhouseCluster,
    migration: Any,
    database: str,
    migration_number: int,
    migration_name: str,
    dry_run: bool = False,
) -> bool:
    """Returns True if all rollback steps succeeded. On partial failure: halts."""
    steps = migration.get_rollback_steps()
    tracking_table_dropped = False

    # Resolve tracking cluster once for all recording calls.
    tracking_cluster: Any = None
    if not dry_run:
        try:
            tracking_cluster = _get_tracking_cluster()
        except Exception:
            logger.debug("Could not resolve tracking cluster for rollback %s", migration_name)

    for step_index, (step, rendered_sql) in enumerate(steps):
        checksum = compute_checksum(rendered_sql)
        drops_tracking_table = _drops_tracking_table(rendered_sql, database)

        try:
            host_results = execute_migration_step(cluster, step, rendered_sql)
        except Exception as exc:
            logger.exception(
                "Rollback %s step %d failed: %s",
                migration_name,
                step_index,
                exc,
            )
            if not dry_run:
                _record_for_tracking(
                    record=StepRecord(
                        migration_number=migration_number,
                        migration_name=migration_name,
                        step_index=step_index,
                        host="unknown",
                        node_role=",".join(step.node_roles),
                        direction="down",
                        checksum=checksum,
                        success=False,
                    ),
                    database=database,
                    _tracking_cluster=tracking_cluster,
                )
            return False

        if not dry_run and not tracking_table_dropped and not drops_tracking_table:
            for host_key in host_results:
                _record_for_tracking(
                    record=StepRecord(
                        migration_number=migration_number,
                        migration_name=migration_name,
                        step_index=step_index,
                        host=str(host_key),
                        node_role=",".join(step.node_roles),
                        direction="down",
                        checksum=checksum,
                        success=True,
                    ),
                    database=database,
                    _tracking_cluster=tracking_cluster,
                )

        if drops_tracking_table:
            tracking_table_dropped = True

    if not dry_run and not tracking_table_dropped:
        _record_for_tracking(
            record=StepRecord(
                migration_number=migration_number,
                migration_name=migration_name,
                step_index=MIGRATION_COMPLETE_STEP,
                host="*",
                node_role="*",
                direction="down",
                checksum="rollback",
                success=True,
            ),
            database=database,
            _tracking_cluster=tracking_cluster,
        )

    return True


def compute_checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode()).hexdigest()


def check_active_mutations(
    cluster: ClickhouseCluster,
    database: str,
    tables: list[str],
) -> list[dict[str, Any]]:
    if not tables:
        return []

    for t in tables:
        if not _SAFE_TABLE_NAME_RE.match(t):
            raise ValueError(f"Invalid table name for mutation check: {t!r}")
    table_list = ", ".join(f"'{t}'" for t in tables)
    sql = (
        f"SELECT database, table, mutation_id, command, create_time "
        f"FROM system.mutations "
        f"WHERE is_done = 0 AND database = '{database}' AND table IN ({table_list}) "
        f"ORDER BY create_time"
    )

    from posthog.clickhouse.client.connection import NodeRole
    from posthog.clickhouse.cluster import Query

    query = Query(sql)
    futures_map = cluster.map_hosts_by_roles(query, node_roles=[NodeRole("data")])
    host_results = futures_map.result()

    active: list[dict[str, Any]] = []
    for _host, rows in host_results.items():
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    active.append(row)
    return active
