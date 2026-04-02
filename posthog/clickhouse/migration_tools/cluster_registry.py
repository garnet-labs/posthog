"""Maps logical cluster names (from schema YAML) to ClickHouse connection settings.

Each schema YAML declares a ``cluster:`` field (e.g. ``main``, ``logs``).
This registry resolves that name to the Django settings that hold the host
and cluster-name for that ClickHouse instance, so ch_migrate can connect
to the right place.
"""

from __future__ import annotations

from posthog.clickhouse.cluster import ClickhouseCluster, get_cluster

# (host_setting_name, cluster_name_setting_name)
# Each PostHog ClickHouse installation may have its own ZooKeeper ensemble.
# The host setting determines which ZK's system.clusters is queried.
_REGISTRY: dict[str, tuple[str, str]] = {
    "main": ("CLICKHOUSE_HOST", "CLICKHOUSE_CLUSTER"),
    "logs": ("CLICKHOUSE_LOGS_CLUSTER_HOST", "CLICKHOUSE_LOGS_CLUSTER"),
    "migrations": ("CLICKHOUSE_MIGRATIONS_HOST", "CLICKHOUSE_MIGRATIONS_CLUSTER"),
    "endpoints": ("CLICKHOUSE_ENDPOINTS_HOST", "CLICKHOUSE_CLUSTER"),
    "single_shard": ("CLICKHOUSE_HOST", "CLICKHOUSE_SINGLE_SHARD_CLUSTER"),
    "writable": ("CLICKHOUSE_HOST", "CLICKHOUSE_WRITABLE_CLUSTER"),
    "primary_replica": ("CLICKHOUSE_HOST", "CLICKHOUSE_PRIMARY_REPLICA_CLUSTER"),
}


def get_cluster_for(logical_name: str) -> ClickhouseCluster:
    """Return a ClickhouseCluster for *logical_name*.

    Falls back to the default cluster when the name isn't registered.
    """
    if logical_name not in _REGISTRY:
        return get_cluster()

    from django.conf import settings

    host_attr, cluster_attr = _REGISTRY[logical_name]
    host = getattr(settings, host_attr, settings.CLICKHOUSE_HOST)
    cluster_name = getattr(settings, cluster_attr, settings.CLICKHOUSE_CLUSTER)
    return get_cluster(host=host, cluster=cluster_name)


def get_all_cluster_names() -> list[str]:
    """Return all known logical cluster names, sorted."""
    return sorted(_REGISTRY.keys())


def validate_cluster_name(name: str) -> bool:
    """Check whether *name* is a registered cluster."""
    return name in _REGISTRY
