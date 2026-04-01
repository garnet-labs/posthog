from __future__ import annotations

from enum import Enum
from typing import Any

from posthog.clickhouse.migration_tools.manifest import ManifestStep
from posthog.clickhouse.migration_tools.schema_graph import get_ecosystem_by_name

KAFKA_SKIP_BROKEN_MESSAGES = 100
HOT_TO_COLD_POLICY = "hot_to_cold"


class MigrationTemplate(Enum):
    INGESTION_PIPELINE = "ingestion_pipeline"
    SHARDED_TABLE = "sharded_table"
    ADD_COLUMN = "add_column"
    CROSS_CLUSTER_READABLE = "cross_cluster_readable"
    MATERIALIZED_VIEW = "materialized_view"
    DROP_TABLE = "drop_table"


def _columns_sql(columns: list[dict[str, str]]) -> str:
    """Build column definitions from a list of {name, type, default?, codec?} dicts."""
    parts = []
    for col in columns:
        line = f"    {col['name']} {col['type']}"
        if "default" in col:
            line += f" DEFAULT {col['default']}"
        if "codec" in col:
            line += f" CODEC({col['codec']})"
        parts.append(line)
    return ",\n".join(parts)


def _order_by_sql(order_by: list[str]) -> str:
    return ", ".join(order_by)


def _build_engine_clauses(
    partition_by: str, storage_policy: bool, ttl: str, extra_settings: str
) -> tuple[str, str, str, str]:
    partition_clause = f"\nPARTITION BY {partition_by}" if partition_by else ""
    storage_clause = f"\nSETTINGS storage_policy = '{HOT_TO_COLD_POLICY}'" if storage_policy else ""
    ttl_clause = f"\n{ttl}" if ttl else ""
    settings_clause = f"\n{extra_settings}" if extra_settings else ""
    return partition_clause, storage_clause, ttl_clause, settings_clause


def _build_sharded_distributed_triple(
    table: str,
    cols_sql: str,
    order_by_clause: str,
    engine_call: str,
    partition_clause: str,
    storage_clause: str,
    ttl_clause: str,
    settings_clause: str,
    sharding_key: str,
    extra_columns: str = "",
) -> list[tuple[ManifestStep, str]]:
    """Generate the sharded + writable + readable table triple."""
    extra_col_block = extra_columns if extra_columns else ""

    sharded_sql = (
        f"CREATE TABLE IF NOT EXISTS {{{{ database }}}}.sharded_{table}\n"
        f"(\n{cols_sql}\n"
        f"{extra_col_block}"
        f") ENGINE = {engine_call}{partition_clause}\n"
        f"ORDER BY ({order_by_clause})"
        f"{ttl_clause}{storage_clause}{settings_clause}"
    )
    sharded_step = ManifestStep(
        sql=f"_template:sharded_{table}",
        node_roles=["DATA"],
        comment=f"Sharded local table for {table}",
        sharded=True,
    )

    writable_sql = (
        f"CREATE TABLE IF NOT EXISTS {{{{ database }}}}.writable_{table}\n"
        f"(\n{cols_sql}\n"
        f"{extra_col_block}"
        f") ENGINE = Distributed('{{{{ cluster }}}}', '{{{{ database }}}}', 'sharded_{table}', {sharding_key})"
    )
    writable_step = ManifestStep(
        sql=f"_template:writable_{table}",
        node_roles=["COORDINATOR"],
        comment=f"Writable distributed table for {table}",
    )

    readable_sql = (
        f"CREATE TABLE IF NOT EXISTS {{{{ database }}}}.{table}\n"
        f"(\n{cols_sql}\n"
        f"{extra_col_block}"
        f") ENGINE = Distributed('{{{{ cluster }}}}', '{{{{ database }}}}', 'sharded_{table}', {sharding_key})"
    )
    readable_step = ManifestStep(
        sql=f"_template:{table}",
        node_roles=["ALL"],
        comment=f"Readable distributed table for {table}",
    )

    return [
        (sharded_step, sharded_sql),
        (writable_step, writable_sql),
        (readable_step, readable_sql),
    ]


def _build_drop_steps(
    objects: list[tuple[str, str, list[str], bool]],
) -> list[tuple[ManifestStep, str]]:
    """Generate DROP steps for a list of (name, obj_type, roles, sharded) tuples."""
    steps = []
    for obj_name, obj_type, roles, sharded in objects:
        sql = f"DROP {obj_type} IF EXISTS {{{{ database }}}}.{obj_name}"
        step = ManifestStep(
            sql=f"_template:drop_{obj_name}",
            node_roles=roles,
            comment=f"Drop {obj_name}",
            sharded=sharded,
        )
        steps.append((step, sql))
    return steps


def _generate_ingestion_pipeline(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    table = config["table"]
    columns = config["columns"]
    order_by = config["order_by"]
    partition_by = config.get("partition_by", "")
    engine = config.get("engine", "ReplicatedMergeTree")
    engine_params = config.get("engine_params", "")
    sharding_key = config.get("sharding_key", "rand()")
    kafka_topic = config["kafka_topic"]
    kafka_group = config.get("kafka_group", f"{table}_consumer")
    kafka_format = config.get("kafka_format", "JSONEachRow")
    storage_policy = config.get("storage_policy", False)
    ttl = config.get("ttl", "")
    extra_settings = config.get("settings", "")
    ingestion_role = config.get("ingestion_role", "INGESTION_EVENTS")

    cols_sql = _columns_sql(columns)
    col_names = ", ".join(col["name"] for col in columns)
    order_by_clause = _order_by_sql(order_by)
    engine_call = f"{engine}({engine_params})" if engine_params else f"{engine}()"

    # 1. Kafka table
    kafka_sql = (
        f"CREATE TABLE IF NOT EXISTS {{{{ database }}}}.kafka_{table}\n"
        f"(\n{cols_sql}\n"
        f") ENGINE = Kafka()\n"
        f"SETTINGS\n"
        f"    kafka_broker_list = '{{{{ kafka_brokers | default(\"kafka:9092\") }}}}',\n"
        f"    kafka_topic_list = '{kafka_topic}',\n"
        f"    kafka_group_name = '{kafka_group}',\n"
        f"    kafka_format = '{kafka_format}',\n"
        f"    kafka_skip_broken_messages = {KAFKA_SKIP_BROKEN_MESSAGES}"
    )

    kafka_step = ManifestStep(
        sql=f"_template:kafka_{table}",
        node_roles=[ingestion_role],
        comment=f"Kafka table for {table}",
    )

    # 2-4. Sharded + writable + readable tables
    partition_clause, storage_clause, ttl_clause, settings_clause = _build_engine_clauses(
        partition_by, storage_policy, ttl, extra_settings
    )

    triple = _build_sharded_distributed_triple(
        table=table,
        cols_sql=cols_sql,
        order_by_clause=order_by_clause,
        engine_call=engine_call,
        partition_clause=partition_clause,
        storage_clause=storage_clause,
        ttl_clause=ttl_clause,
        settings_clause=settings_clause,
        sharding_key=sharding_key,
        extra_columns="    , _timestamp DateTime\n    , _offset UInt64\n",
    )
    sharded_step, sharded_sql = triple[0]
    writable_step, writable_sql = triple[1]
    readable_step, readable_sql = triple[2]

    # 5. Materialized view
    mv_sql = (
        f"CREATE MATERIALIZED VIEW IF NOT EXISTS {{{{ database }}}}.{table}_mv\n"
        f"TO {{{{ database }}}}.writable_{table}\n"
        f"AS SELECT\n"
        f"{col_names},\n"
        f"_timestamp,\n"
        f"_offset\n"
        f"FROM {{{{ database }}}}.kafka_{table}"
    )

    mv_step = ManifestStep(
        sql=f"_template:{table}_mv",
        node_roles=[ingestion_role],
        comment=f"MV from kafka to writable for {table}",
    )

    return [
        (kafka_step, kafka_sql),
        (sharded_step, sharded_sql),
        (writable_step, writable_sql),
        (readable_step, readable_sql),
        (mv_step, mv_sql),
    ]


def _generate_ingestion_pipeline_rollback(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    table = config["table"]
    ingestion_role = config.get("ingestion_role", "INGESTION_EVENTS")

    return _build_drop_steps(
        [
            (f"{table}_mv", "MATERIALIZED VIEW", [ingestion_role], False),
            (table, "TABLE", ["ALL"], False),
            (f"writable_{table}", "TABLE", ["COORDINATOR"], False),
            (f"sharded_{table}", "TABLE", ["DATA"], True),
            (f"kafka_{table}", "TABLE", [ingestion_role], False),
        ]
    )


def _generate_sharded_table(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    table = config["table"]
    columns = config["columns"]
    order_by = config["order_by"]
    partition_by = config.get("partition_by", "")
    engine = config.get("engine", "ReplicatedMergeTree")
    engine_params = config.get("engine_params", "")
    sharding_key = config.get("sharding_key", "rand()")
    storage_policy = config.get("storage_policy", False)
    ttl = config.get("ttl", "")
    extra_settings = config.get("settings", "")

    cols_sql = _columns_sql(columns)
    order_by_clause = _order_by_sql(order_by)
    engine_call = f"{engine}({engine_params})" if engine_params else f"{engine}()"
    partition_clause, storage_clause, ttl_clause, settings_clause = _build_engine_clauses(
        partition_by, storage_policy, ttl, extra_settings
    )

    return _build_sharded_distributed_triple(
        table=table,
        cols_sql=cols_sql,
        order_by_clause=order_by_clause,
        engine_call=engine_call,
        partition_clause=partition_clause,
        storage_clause=storage_clause,
        ttl_clause=ttl_clause,
        settings_clause=settings_clause,
        sharding_key=sharding_key,
    )


def _generate_sharded_table_rollback(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    table = config["table"]
    return _build_drop_steps(
        [
            (table, "TABLE", ["ALL"], False),
            (f"writable_{table}", "TABLE", ["COORDINATOR"], False),
            (f"sharded_{table}", "TABLE", ["DATA"], True),
        ]
    )


def _generate_add_column(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    ecosystem_name = config["ecosystem"]
    column = config["column"]
    after = config.get("after", "")

    eco = get_ecosystem_by_name(ecosystem_name)
    if eco is None:
        raise ValueError(f"Unknown ecosystem '{ecosystem_name}'. Check schema_graph.py for known ecosystems.")

    col_name = column["name"]
    col_type = column["type"]
    col_default = column.get("default", "")
    after_clause = f" AFTER {after}" if after else ""
    default_clause = f" DEFAULT {col_default}" if col_default else ""

    alter_clause = f"ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause}{after_clause}"

    steps: list[tuple[ManifestStep, str]] = []

    # 1. Drop MV if ecosystem has one (so column change doesn't conflict with in-flight inserts)
    if eco.materialized_view:
        drop_mv_sql = f"DROP TABLE IF EXISTS {{{{ database }}}}.{eco.materialized_view}"
        drop_mv_step = ManifestStep(
            sql=f"_template:drop_mv_{eco.materialized_view}",
            node_roles=["ALL"],
            comment=f"Drop MV {eco.materialized_view} before altering columns",
        )
        steps.append((drop_mv_step, drop_mv_sql))

    # 2. ALTER sharded table
    alter_sharded_sql = f"ALTER TABLE {{{{ database }}}}.{eco.sharded_table} {alter_clause}"
    alter_sharded_step = ManifestStep(
        sql=f"_template:alter_sharded_{eco.sharded_table}",
        node_roles=["DATA"],
        comment=f"Add {col_name} to {eco.sharded_table}",
        sharded=True,
        is_alter_on_replicated_table=True,
    )
    steps.append((alter_sharded_step, alter_sharded_sql))

    # 3. ALTER writable distributed (if exists)
    if eco.distributed_writable:
        alter_writable_sql = f"ALTER TABLE {{{{ database }}}}.{eco.distributed_writable} {alter_clause}"
        alter_writable_step = ManifestStep(
            sql=f"_template:alter_writable_{eco.distributed_writable}",
            node_roles=["COORDINATOR"],
            comment=f"Add {col_name} to {eco.distributed_writable}",
        )
        steps.append((alter_writable_step, alter_writable_sql))

    # 4. ALTER readable distributed (if exists and different from sharded)
    if eco.distributed_readable and eco.distributed_readable != eco.sharded_table:
        alter_readable_sql = f"ALTER TABLE {{{{ database }}}}.{eco.distributed_readable} {alter_clause}"
        alter_readable_step = ManifestStep(
            sql=f"_template:alter_readable_{eco.distributed_readable}",
            node_roles=["ALL"],
            comment=f"Add {col_name} to {eco.distributed_readable}",
        )
        steps.append((alter_readable_step, alter_readable_sql))

    # 5. ALTER kafka table (if exists — column must match for MV SELECT *)
    if eco.kafka_table:
        alter_kafka_sql = f"ALTER TABLE {{{{ database }}}}.{eco.kafka_table} {alter_clause}"
        alter_kafka_step = ManifestStep(
            sql=f"_template:alter_kafka_{eco.kafka_table}",
            node_roles=["ALL"],
            comment=f"Add {col_name} to {eco.kafka_table}",
        )
        steps.append((alter_kafka_step, alter_kafka_sql))

    # 6. Recreate MV — use live MV SELECT from config if provided, otherwise placeholder
    if eco.materialized_view:
        mv_select = config.get("mv_select", "")
        if mv_select:
            recreate_mv_sql = (
                f"CREATE MATERIALIZED VIEW IF NOT EXISTS {{{{ database }}}}.{eco.materialized_view}\n"
                f"TO {{{{ database }}}}.{eco.distributed_writable or eco.sharded_table}\n"
                f"AS {mv_select}"
            )
            comment = f"Recreate MV {eco.materialized_view} with new column"
        else:
            recreate_mv_sql = (
                f"-- MV SELECT not provided. Run 'ch_migrate schema' to get the current MV definition,\n"
                f"-- then pass it via mv_select in the template config.\n"
                f"-- CREATE MATERIALIZED VIEW IF NOT EXISTS {{{{ database }}}}.{eco.materialized_view}\n"
                f"-- TO {{{{ database }}}}.{eco.distributed_writable or eco.sharded_table}\n"
                f"-- AS SELECT *, {col_name} FROM {{{{ database }}}}.{eco.kafka_table or '...'}"
            )
            comment = f"Recreate MV {eco.materialized_view} — provide mv_select in config or edit manually"
        recreate_mv_step = ManifestStep(
            sql=f"_template:recreate_mv_{eco.materialized_view}",
            node_roles=["ALL"],
            comment=comment,
        )
        steps.append((recreate_mv_step, recreate_mv_sql))

    return steps


def _generate_add_column_rollback(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    ecosystem_name = config["ecosystem"]
    column = config["column"]

    eco = get_ecosystem_by_name(ecosystem_name)
    if eco is None:
        raise ValueError(f"Unknown ecosystem '{ecosystem_name}'.")

    col_name = column["name"]
    drop_clause = f"DROP COLUMN IF EXISTS {col_name}"

    steps: list[tuple[ManifestStep, str]] = []

    # Reverse order: drop MV, drop column from all tables, recreate MV
    if eco.materialized_view:
        drop_mv_sql = f"DROP TABLE IF EXISTS {{{{ database }}}}.{eco.materialized_view}"
        steps.append(
            (
                ManifestStep(
                    sql=f"_template:rollback_drop_mv_{eco.materialized_view}",
                    node_roles=["ALL"],
                    comment="Drop MV before rolling back column",
                ),
                drop_mv_sql,
            )
        )

    if eco.kafka_table:
        steps.append(
            (
                ManifestStep(
                    sql=f"_template:rollback_alter_kafka_{eco.kafka_table}",
                    node_roles=["ALL"],
                    comment=f"Drop {col_name} from {eco.kafka_table}",
                ),
                f"ALTER TABLE {{{{ database }}}}.{eco.kafka_table} {drop_clause}",
            )
        )

    if eco.distributed_readable and eco.distributed_readable != eco.sharded_table:
        steps.append(
            (
                ManifestStep(
                    sql=f"_template:rollback_alter_readable_{eco.distributed_readable}",
                    node_roles=["ALL"],
                    comment=f"Drop {col_name} from {eco.distributed_readable}",
                ),
                f"ALTER TABLE {{{{ database }}}}.{eco.distributed_readable} {drop_clause}",
            )
        )

    if eco.distributed_writable:
        steps.append(
            (
                ManifestStep(
                    sql=f"_template:rollback_alter_writable_{eco.distributed_writable}",
                    node_roles=["COORDINATOR"],
                    comment=f"Drop {col_name} from {eco.distributed_writable}",
                ),
                f"ALTER TABLE {{{{ database }}}}.{eco.distributed_writable} {drop_clause}",
            )
        )

    steps.append(
        (
            ManifestStep(
                sql=f"_template:rollback_alter_sharded_{eco.sharded_table}",
                node_roles=["DATA"],
                comment=f"Drop {col_name} from {eco.sharded_table}",
                sharded=True,
                is_alter_on_replicated_table=True,
            ),
            f"ALTER TABLE {{{{ database }}}}.{eco.sharded_table} {drop_clause}",
        )
    )

    if eco.materialized_view:
        mv_select = config.get("mv_select", "")
        if mv_select:
            rollback_mv_sql = (
                f"CREATE MATERIALIZED VIEW IF NOT EXISTS {{{{ database }}}}.{eco.materialized_view}\n"
                f"TO {{{{ database }}}}.{eco.distributed_writable or eco.sharded_table}\n"
                f"AS {mv_select}"
            )
            mv_comment = f"Recreate original MV {eco.materialized_view}"
        else:
            rollback_mv_sql = (
                f"-- MV SELECT not provided. Use 'ch_migrate schema' to get the original definition.\n"
                f"-- CREATE MATERIALIZED VIEW IF NOT EXISTS {{{{ database }}}}.{eco.materialized_view}\n"
                f"-- TO {{{{ database }}}}.{eco.distributed_writable or eco.sharded_table}\n"
                f"-- AS SELECT ... FROM {{{{ database }}}}.{eco.kafka_table or '...'}"
            )
            mv_comment = f"Recreate original MV {eco.materialized_view} — provide mv_select or edit"
        steps.append(
            (
                ManifestStep(
                    sql=f"_template:rollback_recreate_mv_{eco.materialized_view}",
                    node_roles=["ALL"],
                    comment=mv_comment,
                ),
                rollback_mv_sql,
            )
        )

    return steps


def _generate_cross_cluster_readable(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    source_table = config["source_table"]
    source_cluster = config["source_cluster"]
    target_cluster = config["target_cluster"]
    create_dictionary = config.get("create_dictionary", False)
    dict_layout = config.get("dict_layout", "flat")
    dict_lifetime = config.get("dict_lifetime", 300)

    steps: list[tuple[ManifestStep, str]] = []

    # 1. Distributed table on target cluster reading from source cluster
    dist_sql = (
        f"CREATE TABLE IF NOT EXISTS {{{{ database }}}}.{source_table}\n"
        f"ENGINE = Distributed('{source_cluster}', '{{{{ database }}}}', '{source_table}')"
    )
    dist_step = ManifestStep(
        sql=f"_template:cross_cluster_{source_table}",
        node_roles=["ALL"],
        clusters=[target_cluster],
        comment=f"Distributed table on {target_cluster} reading from {source_cluster}.{source_table}",
    )
    steps.append((dist_step, dist_sql))

    # 2. Optional dictionary
    if create_dictionary:
        dict_sql = (
            f"CREATE DICTIONARY IF NOT EXISTS {{{{ database }}}}.{source_table}_dict\n"
            f"(\n"
            f"    -- IMPORTANT: Define dictionary columns here.\n"
            f"    -- Example: id UInt64, name String\n"
            f")\n"
            f"PRIMARY KEY id\n"
            f"SOURCE(CLICKHOUSE(\n"
            f"    TABLE '{source_table}'\n"
            f"    DB '{{{{ database }}}}'\n"
            f"))\n"
            f"LAYOUT({dict_layout.upper()}())\n"
            f"LIFETIME({dict_lifetime})"
        )
        dict_step = ManifestStep(
            sql=f"_template:dict_{source_table}_dict",
            node_roles=["ALL"],
            clusters=[target_cluster],
            comment=f"Dictionary for {source_table} on {target_cluster}",
        )
        steps.append((dict_step, dict_sql))

    return steps


def _generate_cross_cluster_readable_rollback(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    source_table = config["source_table"]
    target_cluster = config["target_cluster"]
    create_dictionary = config.get("create_dictionary", False)

    steps: list[tuple[ManifestStep, str]] = []

    if create_dictionary:
        steps.append(
            (
                ManifestStep(
                    sql=f"_template:drop_dict_{source_table}_dict",
                    node_roles=["ALL"],
                    clusters=[target_cluster],
                    comment=f"Drop dictionary {source_table}_dict",
                ),
                f"DROP DICTIONARY IF EXISTS {{{{ database }}}}.{source_table}_dict",
            )
        )

    steps.append(
        (
            ManifestStep(
                sql=f"_template:drop_cross_cluster_{source_table}",
                node_roles=["ALL"],
                clusters=[target_cluster],
                comment=f"Drop cross-cluster distributed table {source_table}",
            ),
            f"DROP TABLE IF EXISTS {{{{ database }}}}.{source_table}",
        )
    )

    return steps


def _generate_materialized_view(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    mv_name = config["name"]
    target_table = config["target_table"]
    source_table = config["source_table"]
    select_columns = config.get("select_columns", "*")
    node_roles = config.get("node_roles", ["ALL"])

    mv_sql = (
        f"CREATE MATERIALIZED VIEW IF NOT EXISTS {{{{ database }}}}.{mv_name}\n"
        f"TO {{{{ database }}}}.{target_table}\n"
        f"AS SELECT {select_columns}\n"
        f"FROM {{{{ database }}}}.{source_table}"
    )

    mv_step = ManifestStep(
        sql=f"_template:mv_{mv_name}",
        node_roles=node_roles,
        comment=f"MV {mv_name} from {source_table} to {target_table}",
    )

    return [(mv_step, mv_sql)]


def _generate_materialized_view_rollback(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    mv_name = config["name"]
    node_roles = config.get("node_roles", ["ALL"])

    return [
        (
            ManifestStep(
                sql=f"_template:drop_mv_{mv_name}",
                node_roles=node_roles,
                comment=f"Drop MV {mv_name}",
            ),
            f"DROP TABLE IF EXISTS {{{{ database }}}}.{mv_name}",
        )
    ]


def _generate_drop_table(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    ecosystem_name = config.get("ecosystem")
    tables = config.get("tables")

    if ecosystem_name:
        eco = get_ecosystem_by_name(ecosystem_name)
        if eco is None:
            raise ValueError(f"Unknown ecosystem '{ecosystem_name}'.")

        # Drop in reverse dependency order: MV -> distributed -> sharded -> kafka
        drop_order: list[tuple[str, str, list[str], bool]] = []
        if eco.materialized_view:
            drop_order.append((eco.materialized_view, "TABLE", ["ALL"], False))
        for d in eco.dictionaries:
            drop_order.append((d.dict_name, "DICTIONARY", ["ALL"], False))
        if eco.distributed_readable and eco.distributed_readable != eco.sharded_table:
            drop_order.append((eco.distributed_readable, "TABLE", ["ALL"], False))
        if eco.distributed_writable:
            drop_order.append((eco.distributed_writable, "TABLE", ["COORDINATOR"], False))
        drop_order.append((eco.sharded_table, "TABLE", ["DATA"], True))
        if eco.kafka_table:
            drop_order.append((eco.kafka_table, "TABLE", ["ALL"], False))

        return _build_drop_steps(drop_order)

    elif tables:
        return _build_drop_steps(
            [
                (
                    tbl["name"],
                    tbl.get("type", "TABLE"),
                    tbl.get("node_roles", ["ALL"]),
                    tbl.get("sharded", False),
                )
                for tbl in tables
            ]
        )

    else:
        raise ValueError("DROP_TABLE requires either 'ecosystem' or 'tables' in config.")


def _generate_drop_table_rollback(config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    # DROP_TABLE rollback is creating — too complex to auto-generate
    return []


_GENERATORS: dict[str, tuple] = {
    MigrationTemplate.INGESTION_PIPELINE.value: (_generate_ingestion_pipeline, _generate_ingestion_pipeline_rollback),
    MigrationTemplate.SHARDED_TABLE.value: (_generate_sharded_table, _generate_sharded_table_rollback),
    MigrationTemplate.ADD_COLUMN.value: (_generate_add_column, _generate_add_column_rollback),
    MigrationTemplate.CROSS_CLUSTER_READABLE.value: (
        _generate_cross_cluster_readable,
        _generate_cross_cluster_readable_rollback,
    ),
    MigrationTemplate.MATERIALIZED_VIEW.value: (_generate_materialized_view, _generate_materialized_view_rollback),
    MigrationTemplate.DROP_TABLE.value: (_generate_drop_table, _generate_drop_table_rollback),
}


def generate_steps(template: str, config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    """Generate forward migration steps from a template type and config."""
    gen = _GENERATORS.get(template)
    if gen is None:
        raise ValueError(f"Unknown template '{template}'. Valid templates: {sorted(_GENERATORS.keys())}")
    return gen[0](config)


def generate_rollback_steps(template: str, config: dict[str, Any]) -> list[tuple[ManifestStep, str]]:
    """Generate rollback migration steps from a template type and config."""
    gen = _GENERATORS.get(template)
    if gen is None:
        raise ValueError(f"Unknown template '{template}'. Valid templates: {sorted(_GENERATORS.keys())}")
    return gen[1](config)
