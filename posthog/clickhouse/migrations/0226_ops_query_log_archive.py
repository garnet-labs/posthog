from posthog.clickhouse.client.connection import NodeRole
from posthog.clickhouse.client.migration_tools import run_sql_with_exceptions
from posthog.clickhouse.query_log_archive import (
    OPS_QUERY_LOG_ARCHIVE_DISTRIBUTED_TABLE_SQL,
    OPS_QUERY_LOG_ARCHIVE_MV_SQL,
    OPS_QUERY_LOG_ARCHIVE_TABLE_SQL,
)

operations = [
    # Create replicated data table on OPS cluster
    run_sql_with_exceptions(
        OPS_QUERY_LOG_ARCHIVE_TABLE_SQL(),
        node_roles=[NodeRole.OPS],
    ),
    # Create distributed table on satellite clusters pointing to OPS
    run_sql_with_exceptions(
        OPS_QUERY_LOG_ARCHIVE_DISTRIBUTED_TABLE_SQL(),
        node_roles=[NodeRole.AI_EVENTS, NodeRole.AUX, NodeRole.SESSIONS],
    ),
    # Create MV on satellite clusters to capture local system.query_log
    run_sql_with_exceptions(
        OPS_QUERY_LOG_ARCHIVE_MV_SQL(),
        node_roles=[NodeRole.AI_EVENTS, NodeRole.AUX, NodeRole.OPS, NodeRole.SESSIONS],
    ),
]
