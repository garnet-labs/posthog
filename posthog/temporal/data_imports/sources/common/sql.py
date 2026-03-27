# Re-exports from sql_source for backwards compatibility.
# New code should import from posthog.temporal.data_imports.sources.common.sql_source directly.
from posthog.temporal.data_imports.sources.common.sql_source.typing import (  # noqa: F401
    Column,
    ColumnType,
    Table,
    TableBase,
    TableReference,
    TableSchemas,
)

__all__ = ["Column", "ColumnType", "Table", "TableBase", "TableReference", "TableSchemas"]
