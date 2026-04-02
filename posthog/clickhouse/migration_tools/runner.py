"""Step execution engine -- routes SQL to correct ClickHouse nodes by role."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from posthog.clickhouse.migration_tools.manifest import ROLE_MAP, ManifestStep

if TYPE_CHECKING:
    from posthog.clickhouse.cluster import ClickhouseCluster


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
