"""Source-type adapters for CDC.

Each database engine needs its own adapter that knows how to:
- Create a stream reader (WAL / binlog / change stream)
- Open a management connection (for slot/publication lifecycle)
- Validate prerequisites (wal_level, permissions, PKs)
- Clean up resources (drop slot, drop publication)
- Check replication lag

Currently only Postgres is implemented. When adding MySQL or another engine,
create an adapter in ``sources/<engine>/cdc/adapter.py`` and register it below.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from posthog.temporal.data_imports.cdc.types import CDCStreamReader

    from products.data_warehouse.backend.models import ExternalDataSource


class CDCSourceAdapter(Protocol):
    """Interface that each CDC-capable database engine must implement."""

    def create_reader(self, source: ExternalDataSource) -> CDCStreamReader: ...

    @contextmanager
    def management_connection(self, source: ExternalDataSource, connect_timeout: int = 15) -> Iterator[Any]: ...

    def validate_prerequisites(
        self,
        source: ExternalDataSource,
        management_mode: Literal["posthog", "self_managed"],
        tables: list[str],
        schema: str,
        slot_name: str | None,
        publication_name: str | None,
    ) -> list[str]: ...

    def drop_resources(self, conn: Any, slot_name: str, pub_name: str) -> None: ...

    def get_lag_bytes(self, conn: Any, slot_name: str) -> int | None: ...


def get_cdc_adapter(source: ExternalDataSource) -> CDCSourceAdapter:
    """Return the CDC adapter for the given source's type.

    Raises ValueError if the source type doesn't support CDC.
    """
    from posthog.temporal.data_imports.sources.postgres.cdc.adapter import PostgresCDCAdapter

    adapters: dict[str, CDCSourceAdapter] = {
        "Postgres": PostgresCDCAdapter(),
    }

    adapter = adapters.get(source.source_type)
    if adapter is None:
        raise ValueError(f"CDC is not supported for source type: {source.source_type}")
    return adapter
