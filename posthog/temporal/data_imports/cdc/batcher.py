from __future__ import annotations

from collections import defaultdict

import pyarrow as pa

from posthog.temporal.data_imports.cdc.types import ChangeEvent

# CDC metadata column names — database-agnostic
CDC_OP_COLUMN = "_ph_cdc_op"
CDC_LOG_POSITION_COLUMN = "_ph_cdc_log_position"
CDC_TIMESTAMP_COLUMN = "_ph_cdc_timestamp"
DELETED_COLUMN = "_ph_deleted"
DELETED_AT_COLUMN = "_ph_deleted_at"


class ChangeEventBatcher:
    """Converts ChangeEvent objects into PyArrow tables grouped by table name.

    Each table contains source columns plus CDC metadata columns:
    - _ph_cdc_op: operation type (I/U/D)
    - _ph_cdc_log_position: serialized replication position
    - _ph_cdc_timestamp: commit timestamp
    - _ph_deleted: soft-delete flag (True for D, False for I/U)
    - _ph_deleted_at: timestamp when deleted (null for I/U)
    """

    def __init__(self) -> None:
        self._events: defaultdict[str, list[ChangeEvent]] = defaultdict(list)

    def add(self, event: ChangeEvent) -> None:
        self._events[event.table_name].append(event)

    def flush(self) -> dict[str, pa.Table]:
        """Convert buffered events into PyArrow tables, one per table name.

        Returns empty dict if no events buffered.
        """
        result: dict[str, pa.Table] = {}

        for table_name, events in self._events.items():
            if not events:
                continue
            result[table_name] = _events_to_table(events)

        self._events.clear()
        return result

    @property
    def event_count(self) -> int:
        return sum(len(events) for events in self._events.values())

    @property
    def table_names(self) -> list[str]:
        return list(self._events.keys())


def _events_to_table(events: list[ChangeEvent]) -> pa.Table:
    """Convert a list of ChangeEvents (same table) to a PyArrow table with CDC metadata."""
    # Collect all column names across all events (order-preserving)
    all_columns: dict[str, None] = {}
    for event in events:
        for col_name in event.columns:
            all_columns[col_name] = None
    column_names = list(all_columns.keys())

    # Build column arrays
    source_data: dict[str, list] = {col: [] for col in column_names}
    cdc_ops: list[str] = []
    cdc_positions: list[str] = []
    cdc_timestamps: list[int] = []  # microseconds since epoch
    deleted_flags: list[bool] = []
    deleted_at: list[int | None] = []

    for event in events:
        for col_name in column_names:
            source_data[col_name].append(event.columns.get(col_name))

        cdc_ops.append(event.operation)
        cdc_positions.append(event.position_serialized)
        ts_us = int(event.timestamp.timestamp() * 1_000_000)
        cdc_timestamps.append(ts_us)
        is_delete = event.operation == "D"
        deleted_flags.append(is_delete)
        deleted_at.append(ts_us if is_delete else None)

    # Build PyArrow arrays for source columns
    arrays: list[pa.Array] = []
    fields: list[pa.Field] = []
    for col_name in column_names:
        arr = pa.array(source_data[col_name])
        arrays.append(arr)
        fields.append(pa.field(col_name, arr.type))

    # Add CDC metadata columns
    arrays.append(pa.array(cdc_ops, type=pa.string()))
    fields.append(pa.field(CDC_OP_COLUMN, pa.string()))

    arrays.append(pa.array(cdc_positions, type=pa.string()))
    fields.append(pa.field(CDC_LOG_POSITION_COLUMN, pa.string()))

    arrays.append(pa.array(cdc_timestamps, type=pa.timestamp("us", tz="UTC")))
    fields.append(pa.field(CDC_TIMESTAMP_COLUMN, pa.timestamp("us", tz="UTC")))

    arrays.append(pa.array(deleted_flags, type=pa.bool_()))
    fields.append(pa.field(DELETED_COLUMN, pa.bool_()))

    arrays.append(pa.array(deleted_at, type=pa.timestamp("us", tz="UTC")))
    fields.append(pa.field(DELETED_AT_COLUMN, pa.timestamp("us", tz="UTC")))

    schema = pa.schema(fields)
    return pa.table(arrays, schema=schema)
