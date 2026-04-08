"""Diff desired state against live schema -> sorted list[StateDiff]."""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

from django.conf import settings as django_settings

from posthog.clickhouse.migration_tools.desired_state import (
    _FROM_SETTINGS_SENTINEL,
    ColumnDef,
    DesiredState,
    DesiredTable,
)
from posthog.clickhouse.migration_tools.manifest import engine_tier, is_distributed, is_kafka, is_mergetree, is_mv
from posthog.clickhouse.migration_tools.schema_introspect import TableSchema
from posthog.clickhouse.migration_tools.tracking import TRACKING_TABLE_NAME

logger = logging.getLogger("migrations")


def _normalize_type(t: str) -> str:
    """Normalize a CH column type for comparison.

    CH system.columns strips timezone from DateTime64 types:
    'DateTime64(6, 'UTC')' in YAML → 'DateTime64(6)' in system.columns.
    Also strips trailing whitespace and normalizes case for Nullable/LowCardinality wrappers.
    """
    # Strip timezone from DateTime64(N, 'TZ') → DateTime64(N)
    t = re.sub(r"DateTime64\((\d+),\s*'[^']+'\)", r"DateTime64(\1)", t)
    return t.strip()


# Map of YAML setting keys to Django settings attributes
_SETTINGS_RESOLUTION: dict[str, str] = {
    "kafka_broker_list": "KAFKA_HOSTS_FOR_CLICKHOUSE",
}


def _resolve_setting(key: str) -> str:
    """Resolve a __from_settings__ sentinel to its Django settings value."""
    attr = _SETTINGS_RESOLUTION.get(key)
    if attr:
        val = getattr(django_settings, attr, None)
        if val:
            return ",".join(val) if isinstance(val, list) else str(val)
    # Fallback for local dev
    return "kafka:9092"


@dataclass
class StateDiff:
    action: str
    table: str
    detail: str
    sql: str
    node_roles: list[str]
    sharded: bool = False
    is_alter_on_replicated_table: bool = False
    depends_on: list[str] = field(default_factory=list)


def _columns_sql(columns: list[ColumnDef]) -> str:
    parts = []
    for col in columns:
        line = f"    {col.name} {col.type}"
        if col.default_expression:
            kind = col.default_kind or "DEFAULT"
            line += f" {kind} {col.default_expression}"
        if col.codec:
            line += f" CODEC({col.codec})"
        parts.append(line)
    return ",\n".join(parts)


def _generate_create_sql(
    table: DesiredTable,
    database: str,
    cluster: str,
) -> str:
    cols = _columns_sql(table.columns)

    if is_mv(table.engine):
        target = table.target or ""
        select = (table.select or "SELECT * FROM ???").replace("{{ database }}", database)
        return f"CREATE MATERIALIZED VIEW IF NOT EXISTS {database}.{table.name}\nTO {database}.{target}\nAS {select}"

    if is_distributed(table.engine):
        source = table.source or ""
        sharding = table.sharding_key or "rand()"
        return (
            f"CREATE TABLE IF NOT EXISTS {database}.{table.name}\n"
            f"(\n{cols}\n"
            f") ENGINE = Distributed('{cluster}', '{database}', '{source}', {sharding})"
        )

    if is_kafka(table.engine):
        settings_lines = []
        if table.settings:
            for k, v in table.settings.items():
                resolved = _resolve_setting(k) if str(v) == _FROM_SETTINGS_SENTINEL else v
                settings_lines.append(f"    {k} = '{resolved}'")
        settings_block = ",\n".join(settings_lines)
        return (
            f"CREATE TABLE IF NOT EXISTS {database}.{table.name}\n"
            f"(\n{cols}\n"
            f") ENGINE = Kafka()\n"
            f"SETTINGS\n{settings_block}"
        )

    # MergeTree family — Replicated engines need explicit ZK path + replica.
    # Path uses database.table to be unique per table. The {shard} and {replica} macros
    # are resolved by CH from the server config at CREATE time.
    if "replicated" in table.engine.lower():
        zk_path = f"/clickhouse/tables/{{shard}}/{database}.{table.name}"
        engine_call = f"{table.engine}('{zk_path}', '{{replica}}')"
    else:
        engine_call = f"{table.engine}()"
    partition = f"\nPARTITION BY {table.partition_by}" if table.partition_by else ""
    order_by = f"\nORDER BY ({', '.join(table.order_by)})" if table.order_by else ""

    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{table.name}\n(\n{cols}\n) ENGINE = {engine_call}{partition}{order_by}"
    )


def _collect_drops(
    desired_names: set[str],
    current: dict[str, TableSchema],
    database: str,
) -> list[StateDiff]:
    drops: list[StateDiff] = []
    for table_name in sorted(set(current.keys()) - desired_names):
        drops.append(
            StateDiff(
                action="drop",
                table=table_name,
                detail=f"Table {table_name} exists but is not in desired state",
                sql=f"DROP TABLE IF EXISTS {database}.{table_name}",
                node_roles=["ALL"],
            )
        )
    return drops


def _collect_creates(
    desired: DesiredState,
    current_names: set[str],
    database: str,
    cluster: str,
) -> list[StateDiff]:
    creates: list[StateDiff] = []
    for table_name in sorted(set(desired.tables.keys()) - current_names):
        desired_table = desired.tables[table_name]
        deps = []
        if is_distributed(desired_table.engine) and desired_table.source:
            deps.append(desired_table.source)
        if is_mv(desired_table.engine) and desired_table.target:
            deps.append(desired_table.target)

        creates.append(
            StateDiff(
                action="create",
                table=table_name,
                detail=f"Create {desired_table.engine} table {table_name}",
                sql=_generate_create_sql(desired_table, database, cluster),
                node_roles=desired_table.on_nodes,
                sharded=desired_table.sharded,
                depends_on=deps,
            )
        )
    return creates


def _handle_engine_mismatch(
    table_name: str,
    desired_table: DesiredTable,
    current_table: TableSchema,
    database: str,
    cluster: str,
) -> StateDiff | None:
    if desired_table.engine.lower() == current_table.engine.lower():
        return None
    action = "recreate_mv" if is_mv(desired_table.engine) or is_mv(current_table.engine) else "recreate"
    return StateDiff(
        action=action,
        table=table_name,
        detail=f"Recreate {table_name} (engine changed: {current_table.engine} -> {desired_table.engine})",
        sql=f"DROP TABLE IF EXISTS {database}.{table_name};\n{_generate_create_sql(desired_table, database, cluster)}",
        node_roles=desired_table.on_nodes,
        sharded=desired_table.sharded,
        depends_on=[desired_table.target] if action == "recreate_mv" and desired_table.target else [],
    )


def _handle_mv_select_diff(
    table_name: str,
    desired_table: DesiredTable,
    current_table: TableSchema,
    database: str,
    cluster: str,
) -> tuple[list[StateDiff], list[StateDiff]]:
    drops: list[StateDiff] = []
    alters: list[StateDiff] = []
    if not (is_mv(desired_table.engine) and desired_table.select):
        return drops, alters
    current_select = current_table.as_select if hasattr(current_table, "as_select") else ""
    if current_select and current_select.strip() != desired_table.select.strip():
        drops.append(
            StateDiff(
                action="drop",
                table=table_name,
                detail=f"Drop MV {table_name} (SELECT changed — will recreate)",
                sql=f"DROP TABLE IF EXISTS {database}.{table_name}",
                node_roles=desired_table.on_nodes,
            )
        )
        alters.append(
            StateDiff(
                action="create",
                table=table_name,
                detail=f"Recreate MV {table_name} with updated SELECT",
                sql=_generate_create_sql(desired_table, database, cluster),
                node_roles=desired_table.on_nodes,
            )
        )
    elif not current_select:
        logger.warning(
            "MV %s: SELECT comparison not possible (as_select not available from host). "
            "Verify manually with 'ch_migrate schema'.",
            table_name,
        )
    return drops, alters


def _handle_kafka_dict_recreation(
    table_name: str,
    desired_table: DesiredTable,
    current_table: TableSchema,
    database: str,
    cluster: str,
) -> tuple[list[StateDiff], list[StateDiff]] | None:
    """Returns (drops, creates) if the table needs recreation, None if not applicable."""
    if desired_table.engine.lower() not in ("kafka", "dictionary"):
        return None
    desired_cols = {c.name: c for c in desired_table.columns}
    current_cols = {c.name: c for c in current_table.columns}
    desired_col_types = {n: _normalize_type(c.type) for n, c in desired_cols.items()}
    current_col_types = {n: _normalize_type(c.type) for n, c in current_cols.items()}
    if set(desired_cols.keys()) == set(current_cols.keys()) and desired_col_types == current_col_types:
        return None
    return (
        [
            StateDiff(
                action="drop",
                table=table_name,
                detail=f"Drop {desired_table.engine} table {table_name} (recreate for column change)",
                sql=f"DROP TABLE IF EXISTS {database}.{table_name}",
                node_roles=desired_table.on_nodes,
            )
        ],
        [
            StateDiff(
                action="create",
                table=table_name,
                detail=f"Recreate {desired_table.engine} table {table_name} with updated columns",
                sql=_generate_create_sql(desired_table, database, cluster),
                node_roles=desired_table.on_nodes,
            )
        ],
    )


def _handle_column_alters(
    table_name: str,
    desired_table: DesiredTable,
    current_table: TableSchema,
    database: str,
) -> list[StateDiff]:
    alters: list[StateDiff] = []
    desired_cols = {c.name: c for c in desired_table.columns}
    current_cols = {c.name: c for c in current_table.columns}
    is_replicated = is_mergetree(desired_table.engine) and "replicated" in desired_table.engine.lower()

    for col_name in sorted(set(desired_cols.keys()) - set(current_cols.keys())):
        col = desired_cols[col_name]
        default_clause = ""
        if col.default_expression:
            kind = col.default_kind or "DEFAULT"
            default_clause = f" {kind} {col.default_expression}"
        alters.append(
            StateDiff(
                action="alter_add_column",
                table=table_name,
                detail=f"Add column {col_name} {col.type} to {table_name}",
                sql=f"ALTER TABLE {database}.{table_name} ADD COLUMN IF NOT EXISTS {col_name} {col.type}{default_clause}",
                node_roles=desired_table.on_nodes,
                sharded=desired_table.sharded,
                is_alter_on_replicated_table=is_replicated,
            )
        )

    for col_name in sorted(set(current_cols.keys()) - set(desired_cols.keys())):
        alters.append(
            StateDiff(
                action="alter_drop_column",
                table=table_name,
                detail=f"Drop column {col_name} from {table_name}",
                sql=f"ALTER TABLE {database}.{table_name} DROP COLUMN IF EXISTS {col_name}",
                node_roles=desired_table.on_nodes,
                sharded=desired_table.sharded,
                is_alter_on_replicated_table=is_replicated,
            )
        )

    for col_name in sorted(set(desired_cols.keys()) & set(current_cols.keys())):
        desired_col = desired_cols[col_name]
        current_col = current_cols[col_name]
        if _normalize_type(desired_col.type) != _normalize_type(current_col.type):
            alters.append(
                StateDiff(
                    action="alter_modify_column",
                    table=table_name,
                    detail=f"Modify column {col_name} from {current_col.type} to {desired_col.type} on {table_name}",
                    sql=f"ALTER TABLE {database}.{table_name} MODIFY COLUMN {col_name} {desired_col.type}",
                    node_roles=desired_table.on_nodes,
                    sharded=desired_table.sharded,
                    is_alter_on_replicated_table=is_replicated,
                )
            )

    return alters


def _collect_changes(
    desired: DesiredState,
    current: dict[str, TableSchema],
    database: str,
    cluster: str,
) -> tuple[list[StateDiff], list[StateDiff], list[StateDiff]]:
    """Tables present in both desired and current: engine mismatches, MV SELECT changes, column diffs."""
    drops: list[StateDiff] = []
    alters: list[StateDiff] = []
    recreates: list[StateDiff] = []

    for table_name in sorted(set(desired.tables.keys()) & set(current.keys())):
        desired_table = desired.tables[table_name]
        current_table = current[table_name]

        recreate = _handle_engine_mismatch(table_name, desired_table, current_table, database, cluster)
        if recreate is not None:
            recreates.append(recreate)
            continue

        mv_drops, mv_creates = _handle_mv_select_diff(table_name, desired_table, current_table, database, cluster)
        drops.extend(mv_drops)
        alters.extend(mv_creates)

        kafka_result = _handle_kafka_dict_recreation(table_name, desired_table, current_table, database, cluster)
        if kafka_result is not None:
            kdrop, kcreate = kafka_result
            drops.extend(kdrop)
            alters.extend(kcreate)
            continue

        if is_mv(desired_table.engine):
            continue

        alters.extend(_handle_column_alters(table_name, desired_table, current_table, database))

    return drops, alters, recreates


def _tier_sort_key(desired: DesiredState) -> callable:
    """Sort key for alters and creates: by engine tier then table name."""

    def _key(d: StateDiff) -> tuple[int, str]:
        table = desired.tables.get(d.table)
        tier = engine_tier(table.engine) if table else 1
        return (tier, d.table)

    return _key


def diff_state(
    desired: DesiredState,
    current: dict[str, TableSchema],
    database: str | None = None,
    cluster: str | None = None,
) -> list[StateDiff]:
    """Returns diffs sorted in dependency order: drops, alters, creates, recreates."""
    db = database or desired.database
    cluster_name = cluster or desired.cluster

    desired_names = set(desired.tables.keys())
    current_names = set(current.keys())

    drops = _collect_drops(desired_names, current, db)
    creates = _collect_creates(desired, current_names, db, cluster_name)
    change_drops, alters, recreates = _collect_changes(desired, current, db, cluster_name)
    drops.extend(change_drops)

    max_tier = 3  # MaterializedView/Dictionary — highest tier drops first

    def _drop_sort_key(d: StateDiff) -> tuple[int, str]:
        tier = max_tier - engine_tier(current.get(d.table, TableSchema(name=d.table, engine="")).engine)
        return (tier, d.table)

    sort_key = _tier_sort_key(desired)
    drops.sort(key=_drop_sort_key)
    alters.sort(key=sort_key)
    creates.sort(key=sort_key)

    return drops + alters + creates + recreates


def detect_orphans(
    desired_states: list[DesiredState],
    current: dict[str, TableSchema],
    exclude_patterns: list[str] | None = None,
) -> list[str]:
    declared: set[str] = set()
    for ds in desired_states:
        declared.update(ds.tables.keys())

    default_exclude = {"infi_clickhouse_orm_migrations", TRACKING_TABLE_NAME}
    exclude = default_exclude | set(exclude_patterns or [])

    orphans = []
    for name in current:
        if name in declared or name in exclude:
            continue
        engine = current[name].engine.lower()
        if engine in ("view", "join"):
            continue
        if name.startswith("_tmp") or name.startswith("pending_deletes"):
            continue
        orphans.append(name)

    return sorted(orphans)
