"""Advisory locking for concurrent apply prevention."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NamedTuple

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

LOCK_MIGRATION_NUMBER = 0
# Must not collide with VERSION_STEP_INDEX (-2) or any real step index (>= 0)
LOCK_STEP_INDEX = -999
LOCK_TIMEOUT_MINUTES = 30


@dataclass
class StepRecord:
    migration_number: int
    migration_name: str
    step_index: int
    host: str
    node_role: str
    direction: str
    checksum: str
    success: bool


def ensure_tracking_table(client: Any, database: str) -> None:
    client.execute(TRACKING_TABLE_DDL.format(database=database))


def record_step(
    client: Any,
    record: StepRecord,
    database: str = "",
) -> None:
    table_ref = f"{database}.{TRACKING_TABLE_NAME}" if database else TRACKING_TABLE_NAME
    sql = f"""
        INSERT INTO {table_ref}
        (migration_number, migration_name, step_index, host, node_role, direction, checksum, applied_at, success)
        VALUES
    """
    now = datetime.now(tz=UTC)
    params = [
        (
            record.migration_number,
            record.migration_name,
            record.step_index,
            record.host,
            record.node_role,
            record.direction,
            record.checksum,
            now,
            record.success,
        )
    ]
    client.execute(sql, params)


def acquire_apply_lock(client: Any, database: str, hostname: str, *, force: bool = False) -> tuple[bool, str]:
    """Best-effort: MergeTree is eventually consistent, so two pods in the same merge cycle
    could both acquire. Sufficient for single-deploy-at-a-time."""
    ensure_tracking_table(client, database)
    table_ref = f"{database}.{TRACKING_TABLE_NAME}"

    if force:
        record_step(
            client=client,
            record=StepRecord(
                migration_number=LOCK_MIGRATION_NUMBER,
                migration_name="__lock__",
                step_index=LOCK_STEP_INDEX,
                host=hostname,
                node_role="*",
                direction="up",
                checksum="lock",
                success=True,
            ),
            database=database,
        )
        return (True, "")

    # Atomic: INSERT only if no active lock from another host that hasn't released.
    # A released lock has a success=0, direction='down' row — those hosts are excluded.
    atomic_sql = f"""
        INSERT INTO {table_ref}
        (migration_number, migration_name, step_index, host, node_role, direction, checksum, applied_at, success)
        SELECT
            {LOCK_MIGRATION_NUMBER}, '__lock__', {LOCK_STEP_INDEX},
            %(hostname)s, '*', 'up', 'lock', now64(), 1
        WHERE NOT EXISTS (
            SELECT 1 FROM {table_ref}
            WHERE migration_number = {LOCK_MIGRATION_NUMBER}
              AND step_index = {LOCK_STEP_INDEX}
              AND success = 1
              AND applied_at > now() - INTERVAL {LOCK_TIMEOUT_MINUTES} MINUTE
              AND host != %(hostname)s
              AND host NOT IN (
                  SELECT host FROM {table_ref}
                  WHERE migration_number = {LOCK_MIGRATION_NUMBER}
                    AND step_index = {LOCK_STEP_INDEX}
                    AND success = 0 AND direction = 'down'
                    AND applied_at > now() - INTERVAL {LOCK_TIMEOUT_MINUTES} MINUTE
              )
        )
    """
    client.execute(atomic_sql, {"hostname": hostname})

    # Verify we got the lock by checking if our row is the latest
    verify_sql = f"""
        SELECT host, applied_at
        FROM {table_ref}
        WHERE migration_number = {LOCK_MIGRATION_NUMBER}
          AND step_index = {LOCK_STEP_INDEX}
          AND success = 1
          AND applied_at > now() - INTERVAL {LOCK_TIMEOUT_MINUTES} MINUTE
        ORDER BY applied_at DESC
        LIMIT 1
    """
    rows = client.execute(verify_sql)
    if rows and rows[0][0] != hostname:
        lock_host = rows[0][0]
        lock_time = rows[0][1]
        return (
            False,
            f"Another ch_migrate apply is running on {lock_host} (started {lock_time}). Use --force to override.",
        )

    return (True, "")


class SchemaVersion(NamedTuple):
    commit_hash: str
    host: str
    applied_at: str


# Schema version sentinel: records which git commit was last applied.
VERSION_STEP_INDEX = -2


def record_schema_version(client: Any, database: str, commit_hash: str, hostname: str) -> None:
    record_step(
        client=client,
        record=StepRecord(
            migration_number=LOCK_MIGRATION_NUMBER,
            migration_name=commit_hash,
            step_index=VERSION_STEP_INDEX,
            host=hostname,
            node_role="*",
            direction="up",
            checksum="version",
            success=True,
        ),
        database=database,
    )


def get_latest_schema_version(client: Any, database: str) -> SchemaVersion | None:
    table_ref = f"{database}.{TRACKING_TABLE_NAME}"
    sql = f"""
        SELECT migration_name, host, applied_at
        FROM {table_ref}
        WHERE migration_number = {LOCK_MIGRATION_NUMBER}
          AND step_index = {VERSION_STEP_INDEX}
          AND success = 1
        ORDER BY applied_at DESC
        LIMIT 1
    """
    rows = client.execute(sql)
    if rows:
        return SchemaVersion(commit_hash=rows[0][0], host=rows[0][1], applied_at=str(rows[0][2]))
    return None


def release_apply_lock(client: Any, database: str, hostname: str) -> None:
    """Release the advisory lock by inserting a success=False row that shadows the lock."""
    record_step(
        client=client,
        record=StepRecord(
            migration_number=LOCK_MIGRATION_NUMBER,
            migration_name="__lock__",
            step_index=LOCK_STEP_INDEX,
            host=hostname,
            node_role="*",
            direction="down",
            checksum="unlock",
            success=False,
        ),
        database=database,
    )
