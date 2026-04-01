import logging
from functools import cache
from typing import Optional

from infi.clickhouse_orm import migrations

from posthog import settings
from posthog.clickhouse.client.connection import NodeRole
from posthog.clickhouse.cluster import Query, get_cluster
from posthog.settings.data_stores import CLICKHOUSE_MIGRATIONS_CLUSTER, CLICKHOUSE_MIGRATIONS_HOST

logger = logging.getLogger("migrations")


@cache
def get_migrations_cluster():
    return get_cluster(host=CLICKHOUSE_MIGRATIONS_HOST, cluster=CLICKHOUSE_MIGRATIONS_CLUSTER)


def run_sql_with_exceptions(
    sql: str,
    node_roles: list[NodeRole] | NodeRole | None = None,
    sharded: Optional[bool] = None,
    is_alter_on_replicated_table: Optional[bool] = None,
):
    """Execute SQL on each node with role/shard routing.

    .. deprecated::
        Use manifest.yaml with ``ch_migrate`` instead.
        See ``posthog/clickhouse/migrations/README.md``.
    """
    import warnings

    warnings.warn(
        "run_sql_with_exceptions is deprecated. Use manifest.yaml with ch_migrate. "
        "See posthog/clickhouse/migrations/README.md",
        DeprecationWarning,
        stacklevel=2,
    )

    if node_roles and not isinstance(node_roles, list):
        node_roles = [node_roles]

    node_roles = node_roles or [NodeRole.DATA]

    # Store original node_roles for validation purposes before debug override
    original_node_roles = node_roles

    if settings.E2E_TESTING or settings.DEBUG or not settings.CLOUD_DEPLOYMENT:
        # In E2E tests, debug mode and hobby deployments, we run migrations on ALL nodes
        # because we don't have different ClickHouse topologies yet in Docker
        node_roles = [NodeRole.ALL]

    def run_migration():
        cluster = get_migrations_cluster()

        query = Query(sql)

        if sharded and is_alter_on_replicated_table:
            assert (NodeRole.DATA in node_roles and len(node_roles) == 1) or (
                settings.E2E_TESTING or settings.DEBUG or not settings.CLOUD_DEPLOYMENT
            ), "When running migrations on sharded tables, the node_role must be NodeRole.DATA"
            return cluster.map_one_host_per_shard(query).result()
        elif is_alter_on_replicated_table:
            logger.info("       Running ALTER on replicated table on just one host")
            return cluster.any_host_by_roles(query, node_roles=node_roles).result()
        else:
            return cluster.map_hosts_by_roles(query, node_roles=node_roles).result()

    operation = migrations.RunPython(lambda _: run_migration())

    # Attach metadata for validation tools
    # Use original_node_roles (before debug override) for validation purposes
    operation._sql = sql
    operation._node_roles = original_node_roles
    operation._sharded = sharded
    operation._is_alter_on_replicated_table = is_alter_on_replicated_table

    return operation
