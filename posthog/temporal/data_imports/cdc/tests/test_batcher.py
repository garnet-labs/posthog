from datetime import UTC, datetime

from posthog.temporal.data_imports.cdc.batcher import (
    CDC_LOG_POSITION_COLUMN,
    CDC_OP_COLUMN,
    CDC_TIMESTAMP_COLUMN,
    DELETED_AT_COLUMN,
    DELETED_COLUMN,
    ChangeEventBatcher,
)
from posthog.temporal.data_imports.cdc.types import ChangeEvent


def _make_event(
    op: str = "I",
    table: str = "users",
    position: str = "0/100",
    columns: dict | None = None,
    timestamp: datetime | None = None,
) -> ChangeEvent:
    return ChangeEvent(
        operation=op,
        table_name=table,
        position_serialized=position,
        timestamp=timestamp or datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        columns=columns or {"id": 1, "name": "Alice"},
    )


class TestChangeEventBatcher:
    def test_empty_flush(self):
        batcher = ChangeEventBatcher()
        result = batcher.flush()
        assert result == {}

    def test_insert_event_metadata(self):
        batcher = ChangeEventBatcher()
        batcher.add(_make_event(op="I"))
        tables = batcher.flush()

        assert "users" in tables
        table = tables["users"]
        assert table.num_rows == 1
        assert table.column(CDC_OP_COLUMN)[0].as_py() == "I"
        assert table.column(CDC_LOG_POSITION_COLUMN)[0].as_py() == "0/100"
        assert table.column(DELETED_COLUMN)[0].as_py() is False
        assert table.column(DELETED_AT_COLUMN)[0].as_py() is None

    def test_delete_event_metadata(self):
        ts = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)
        batcher = ChangeEventBatcher()
        batcher.add(_make_event(op="D", timestamp=ts))
        tables = batcher.flush()

        table = tables["users"]
        assert table.column(CDC_OP_COLUMN)[0].as_py() == "D"
        assert table.column(DELETED_COLUMN)[0].as_py() is True
        deleted_at = table.column(DELETED_AT_COLUMN)[0].as_py()
        assert deleted_at == ts

    def test_source_columns_preserved(self):
        batcher = ChangeEventBatcher()
        batcher.add(_make_event(columns={"id": 42, "email": "test@example.com", "score": 99.5}))
        tables = batcher.flush()

        table = tables["users"]
        assert table.column("id")[0].as_py() == 42
        assert table.column("email")[0].as_py() == "test@example.com"
        assert table.column("score")[0].as_py() == 99.5

    def test_grouping_by_table_name(self):
        batcher = ChangeEventBatcher()
        batcher.add(_make_event(table="users", columns={"id": 1}))
        batcher.add(_make_event(table="orders", columns={"id": 100}))
        batcher.add(_make_event(table="users", columns={"id": 2}))
        tables = batcher.flush()

        assert set(tables.keys()) == {"users", "orders"}
        assert tables["users"].num_rows == 2
        assert tables["orders"].num_rows == 1

    def test_mixed_operations_single_table(self):
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        batcher = ChangeEventBatcher()
        batcher.add(_make_event(op="I", columns={"id": 1, "name": "Alice"}, position="0/100", timestamp=ts))
        batcher.add(_make_event(op="U", columns={"id": 1, "name": "Bob"}, position="0/200", timestamp=ts))
        batcher.add(_make_event(op="D", columns={"id": 2}, position="0/300", timestamp=ts))
        tables = batcher.flush()

        table = tables["users"]
        assert table.num_rows == 3

        ops = table.column(CDC_OP_COLUMN).to_pylist()
        assert ops == ["I", "U", "D"]

        positions = table.column(CDC_LOG_POSITION_COLUMN).to_pylist()
        assert positions == ["0/100", "0/200", "0/300"]

        deleted = table.column(DELETED_COLUMN).to_pylist()
        assert deleted == [False, False, True]

    def test_null_source_column_values(self):
        batcher = ChangeEventBatcher()
        batcher.add(_make_event(columns={"id": 1, "name": None}))
        tables = batcher.flush()

        table = tables["users"]
        assert table.column("id")[0].as_py() == 1
        assert table.column("name")[0].as_py() is None

    def test_sparse_columns_across_events(self):
        batcher = ChangeEventBatcher()
        batcher.add(_make_event(columns={"id": 1, "name": "Alice"}))
        batcher.add(_make_event(columns={"id": 2, "email": "bob@test.com"}))
        tables = batcher.flush()

        table = tables["users"]
        assert table.num_rows == 2
        # First event has name but no email
        assert table.column("name")[0].as_py() == "Alice"
        assert table.column("email")[0].as_py() is None
        # Second event has email but no name
        assert table.column("name")[1].as_py() is None
        assert table.column("email")[1].as_py() == "bob@test.com"

    def test_flush_clears_buffer(self):
        batcher = ChangeEventBatcher()
        batcher.add(_make_event())
        assert batcher.event_count == 1

        batcher.flush()
        assert batcher.event_count == 0

        result = batcher.flush()
        assert result == {}

    def test_event_count_and_table_names(self):
        batcher = ChangeEventBatcher()
        batcher.add(_make_event(table="users"))
        batcher.add(_make_event(table="orders"))
        batcher.add(_make_event(table="users"))

        assert batcher.event_count == 3
        assert sorted(batcher.table_names) == ["orders", "users"]

    def test_cdc_timestamp_column(self):
        ts = datetime(2025, 6, 15, 14, 30, 45, 123456, tzinfo=UTC)
        batcher = ChangeEventBatcher()
        batcher.add(_make_event(timestamp=ts))
        tables = batcher.flush()

        table = tables["users"]
        cdc_ts = table.column(CDC_TIMESTAMP_COLUMN)[0].as_py()
        assert cdc_ts == ts

    def test_delete_event_with_sparse_columns(self):
        # PG CDC DELETE events often carry only identity (PK) columns, not all columns.
        batcher = ChangeEventBatcher()
        batcher.add(_make_event(op="I", columns={"id": 1, "name": "Alice", "email": "a@test.com"}))
        batcher.add(_make_event(op="D", columns={"id": 1}))
        tables = batcher.flush()

        table = tables["users"]
        assert table.num_rows == 2
        assert table.column(DELETED_COLUMN)[1].as_py() is True
        # Columns absent from the D event should be null, not missing
        assert table.column("name")[1].as_py() is None
        assert table.column("email")[1].as_py() is None
