from datetime import UTC, datetime
from typing import Any

TRACKING_TABLE_NAME = "clickhouse_schema_migrations"

TRACKING_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS {database}.clickhouse_schema_migrations (
    migration_number UInt32,
    migration_name String,
    step_index Int32,
    host String,
    node_role String,
    direction Enum8('up' = 1, 'down' = 2),
    checksum String,
    applied_at DateTime64(3),
    success Bool
) ENGINE = MergeTree()
ORDER BY (migration_number, step_index, host, direction, applied_at)
"""

# Sentinel step_index used to mark a migration as fully applied.
MIGRATION_COMPLETE_STEP = -1

# Advisory lock constants (used by ch_migrate apply to prevent concurrent runs).
LOCK_MIGRATION_NUMBER = 0
LOCK_STEP_INDEX = -999


def get_tracking_ddl(database: str) -> str:
    return TRACKING_TABLE_DDL.format(database=database)


def record_step(
    client: Any,
    migration_number: int,
    migration_name: str,
    step_index: int,
    host: str,
    node_role: str,
    direction: str,
    checksum: str,
    success: bool,
) -> None:
    sql = f"""
        INSERT INTO {TRACKING_TABLE_NAME}
        (migration_number, migration_name, step_index, host, node_role, direction, checksum, applied_at, success)
        VALUES
    """
    now = datetime.now(tz=UTC)
    params = [
        (
            migration_number,
            migration_name,
            step_index,
            host,
            node_role,
            direction,
            checksum,
            now,
            success,
        )
    ]
    client.execute(sql, params)


def get_step_results(client: Any, database: str, migration_number: int) -> dict[tuple[int, str], bool]:
    """Return per-(step_index, host) success status for a migration.

    Used by the runner to skip hosts that already succeeded during a
    previous (partially-failed) apply attempt.
    """
    sql = f"""
        SELECT step_index, host, success
        FROM {database}.{TRACKING_TABLE_NAME}
        WHERE migration_number = {migration_number}
          AND direction = 'up'
          AND step_index >= 0
        ORDER BY step_index, host
    """
    rows = client.execute(sql)
    return {(row[0], row[1]): bool(row[2]) for row in rows}


def acquire_apply_lock(client: Any, database: str, hostname: str, *, force: bool = False) -> tuple[bool, str]:
    """Try to acquire an advisory lock for ch_migrate apply.

    Returns (acquired, message). If another lock is held within the last
    30 minutes, returns (False, reason). Otherwise inserts a lock row
    and returns (True, "").

    When force=True, skips the existing-lock check and acquires unconditionally.
    """
    if not force:
        # Check for existing lock
        check_sql = f"""
            SELECT host, applied_at
            FROM {database}.{TRACKING_TABLE_NAME}
            WHERE migration_number = {LOCK_MIGRATION_NUMBER}
              AND step_index = {LOCK_STEP_INDEX}
              AND success = 1
              AND applied_at > now() - INTERVAL 30 MINUTE
            ORDER BY applied_at DESC
            LIMIT 1
        """
        rows = client.execute(check_sql)
        if rows:
            lock_host = rows[0][0]
            lock_time = rows[0][1]
            if lock_host != hostname:
                return (
                    False,
                    f"Another ch_migrate apply is running on {lock_host} (started {lock_time}). Use --force to override.",
                )

    # Insert lock row
    record_step(
        client=client,
        migration_number=LOCK_MIGRATION_NUMBER,
        migration_name="__lock__",
        step_index=LOCK_STEP_INDEX,
        host=hostname,
        node_role="*",
        direction="up",
        checksum="lock",
        success=True,
    )
    return (True, "")


def release_apply_lock(client: Any, database: str, hostname: str) -> None:
    """Release the advisory lock by marking it as unsuccessful.

    MergeTree doesn't support DELETE, so we insert a success=False row
    that shadows the lock. The acquire check uses success=1 so the old
    row is effectively ignored.
    """
    record_step(
        client=client,
        migration_number=LOCK_MIGRATION_NUMBER,
        migration_name="__lock__",
        step_index=LOCK_STEP_INDEX,
        host=hostname,
        node_role="*",
        direction="down",
        checksum="unlock",
        success=False,
    )


def get_applied_migrations(client: Any, database: str) -> list[dict[str, Any]]:
    """Return migrations that are currently applied (not rolled back).

    A migration is considered applied when its most recent sentinel record
    (step_index = -1) has direction = 'up'. If a rollback wrote a
    direction = 'down' sentinel after the apply, that migration is excluded.

    Uses ClickHouse's ``argMax(direction, applied_at)`` to pick the
    direction of the newest sentinel per migration.
    """
    sql = f"""
        SELECT
            migration_number,
            migration_name,
            argMax(direction, applied_at) AS latest_direction,
            max(applied_at) AS latest_applied_at
        FROM {database}.{TRACKING_TABLE_NAME}
        WHERE success = 1 AND step_index = {MIGRATION_COMPLETE_STEP}
        GROUP BY migration_number, migration_name
        HAVING latest_direction = 'up'
        ORDER BY migration_number
    """
    rows = client.execute(sql)
    columns = [
        "migration_number",
        "migration_name",
        "direction",
        "applied_at",
    ]
    return [dict(zip(columns, row)) for row in rows]


def get_migration_status_all_hosts(cluster: Any, database: str) -> dict[str, Any]:
    from posthog.clickhouse.cluster import Query

    sql = f"""
        SELECT
            migration_number,
            migration_name,
            max(step_index) AS last_step,
            host,
            direction,
            min(success) AS all_success
        FROM {database}.{TRACKING_TABLE_NAME}
        WHERE direction = 'up'
        GROUP BY migration_number, migration_name, host, direction
        ORDER BY migration_number
    """

    import logging

    logger = logging.getLogger(__name__)
    futures_map = cluster.map_all_hosts(Query(sql))
    results: dict[str, Any] = {}
    try:
        host_results = futures_map.result()
        for host_info, rows in host_results.items():
            host_key = str(host_info)
            results[host_key] = {
                "reachable": True,
                "migrations": rows,
            }
    except ExceptionGroup as eg:
        # Some hosts failed — extract partial results from successful ones
        logger.warning("Some hosts unreachable during status query: %s", eg)
        for exc in eg.exceptions:
            results[str(exc)] = {"reachable": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("Status query failed: %s", exc)

    return results


def get_infi_migration_status(cluster: Any, database: str) -> dict[str, Any]:
    """Query the legacy infi clickhouse_orm migrations table for applied migrations.

    Returns per-host dict similar to get_migration_status_all_hosts.
    """
    from posthog.clickhouse.cluster import Query

    sql = f"""
        SELECT name
        FROM {database}.clickhouseorm_migrations
        ORDER BY name
    """

    results: dict[str, Any] = {}
    try:
        futures_map = cluster.map_all_hosts(Query(sql))
        host_results = futures_map.result()
        for host_info, rows in host_results.items():
            host_key = str(host_info)
            # Rows are tuples like (name,)
            migration_names = [row[0] if isinstance(row, (tuple, list)) else row for row in rows]
            results[host_key] = {
                "reachable": True,
                "migrations": migration_names,
            }
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Failed to query legacy migration table: %s", exc)

    return results
