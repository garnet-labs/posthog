from posthog.clickhouse.client.connection import NodeRole
from posthog.clickhouse.client.migration_tools import run_sql_with_exceptions

from products.error_tracking.backend.indexed_embedding import EMBEDDING_TABLES

operations = []

for model_tables in EMBEDDING_TABLES:
    operations.append(
        run_sql_with_exceptions(
            model_tables.add_content_full_text_index_sql(),
            node_roles=[NodeRole.DATA],
            sharded=True,
            is_alter_on_replicated_table=True,
        )
    )
