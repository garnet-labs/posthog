from datetime import UTC, datetime

from posthog.temporal.data_imports.cdc.batcher import (
    CDC_OP_COLUMN,
    CDC_TIMESTAMP_COLUMN,
    DELETED_AT_COLUMN,
    DELETED_COLUMN,
    SCD2_VALID_FROM_COLUMN,
    SCD2_VALID_TO_COLUMN,
    ChangeEventBatcher,
    build_scd2_table,
    deduplicate_table,
    enrich_delete_rows,
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


class TestDeduplicateTable:
    def _make_raw_table(self, events):
        batcher = ChangeEventBatcher()
        for ev in events:
            batcher.add(ev)
        return batcher.flush()["users"]

    def test_single_event_unchanged(self):
        table = self._make_raw_table([_make_event(op="I", columns={"id": 1})])
        result = deduplicate_table(table, ["id"])
        assert result.num_rows == 1

    def test_two_updates_same_pk_keeps_last(self):
        events = [
            _make_event(op="U", columns={"id": 1, "name": "Alice"}, position="0/100"),
            _make_event(op="U", columns={"id": 1, "name": "Bob"}, position="0/200"),
        ]
        table = self._make_raw_table(events)
        result = deduplicate_table(table, ["id"])
        assert result.num_rows == 1
        assert result.column("name")[0].as_py() == "Bob"

    def test_different_pks_both_kept(self):
        events = [
            _make_event(op="I", columns={"id": 1, "name": "Alice"}),
            _make_event(op="I", columns={"id": 2, "name": "Bob"}),
        ]
        table = self._make_raw_table(events)
        result = deduplicate_table(table, ["id"])
        assert result.num_rows == 2

    def test_insert_then_delete_keeps_delete(self):
        events = [
            _make_event(op="I", columns={"id": 1, "name": "Alice"}, position="0/100"),
            _make_event(op="D", columns={"id": 1}, position="0/200"),
        ]
        table = self._make_raw_table(events)
        result = deduplicate_table(table, ["id"])
        assert result.num_rows == 1
        assert result.column(CDC_OP_COLUMN)[0].as_py() == "D"

    def test_empty_pk_columns_returns_unchanged(self):
        table = self._make_raw_table([_make_event(), _make_event()])
        result = deduplicate_table(table, [])
        assert result.num_rows == 2

    def test_pk_column_not_in_table_returns_unchanged(self):
        table = self._make_raw_table([_make_event(), _make_event()])
        result = deduplicate_table(table, ["nonexistent_col"])
        assert result.num_rows == 2

    def test_preserves_row_order(self):
        events = [
            _make_event(op="I", columns={"id": 2, "name": "Bob"}, position="0/100"),
            _make_event(op="I", columns={"id": 1, "name": "Alice"}, position="0/200"),
        ]
        table = self._make_raw_table(events)
        result = deduplicate_table(table, ["id"])
        # Both PKs distinct, order should be preserved
        assert result.column("id").to_pylist() == [2, 1]


class TestBuildScd2Table:
    def _make_raw_table(self, events):
        batcher = ChangeEventBatcher()
        for ev in events:
            batcher.add(ev)
        return batcher.flush()["users"]

    def test_single_event_valid_to_is_null(self):
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        table = self._make_raw_table([_make_event(op="I", columns={"id": 1}, timestamp=ts)])
        result = build_scd2_table(table, ["id"])
        assert SCD2_VALID_FROM_COLUMN in result.column_names
        assert SCD2_VALID_TO_COLUMN in result.column_names
        assert result.column(SCD2_VALID_FROM_COLUMN)[0].as_py() == ts
        assert result.column(SCD2_VALID_TO_COLUMN)[0].as_py() is None

    def test_two_events_same_pk_valid_to_chain(self):
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        ts2 = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
        events = [
            _make_event(op="I", columns={"id": 1, "name": "Alice"}, position="0/100", timestamp=ts1),
            _make_event(op="U", columns={"id": 1, "name": "Bob"}, position="0/200", timestamp=ts2),
        ]
        table = self._make_raw_table(events)
        result = build_scd2_table(table, ["id"])
        assert result.num_rows == 2
        # First event: valid_to = ts2
        assert result.column(SCD2_VALID_FROM_COLUMN)[0].as_py() == ts1
        assert result.column(SCD2_VALID_TO_COLUMN)[0].as_py() == ts2
        # Last event: valid_to = null
        assert result.column(SCD2_VALID_FROM_COLUMN)[1].as_py() == ts2
        assert result.column(SCD2_VALID_TO_COLUMN)[1].as_py() is None

    def test_three_events_same_pk(self):
        ts1 = datetime(2026, 1, 1, tzinfo=UTC)
        ts2 = datetime(2026, 1, 2, tzinfo=UTC)
        ts3 = datetime(2026, 1, 3, tzinfo=UTC)
        events = [
            _make_event(op="I", columns={"id": 1}, position="0/100", timestamp=ts1),
            _make_event(op="U", columns={"id": 1}, position="0/200", timestamp=ts2),
            _make_event(op="U", columns={"id": 1}, position="0/300", timestamp=ts3),
        ]
        table = self._make_raw_table(events)
        result = build_scd2_table(table, ["id"])
        valid_to = result.column(SCD2_VALID_TO_COLUMN).to_pylist()
        assert valid_to == [ts2, ts3, None]

    def test_delete_is_last_valid_state(self):
        ts1 = datetime(2026, 1, 1, tzinfo=UTC)
        ts2 = datetime(2026, 1, 2, tzinfo=UTC)
        events = [
            _make_event(op="I", columns={"id": 1}, position="0/100", timestamp=ts1),
            _make_event(op="D", columns={"id": 1}, position="0/200", timestamp=ts2),
        ]
        table = self._make_raw_table(events)
        result = build_scd2_table(table, ["id"])
        # DELETE row is the last event → valid_to IS NULL (current state)
        assert result.column(SCD2_VALID_TO_COLUMN)[1].as_py() is None

    def test_different_pks_independent_chains(self):
        ts1 = datetime(2026, 1, 1, tzinfo=UTC)
        ts2 = datetime(2026, 1, 2, tzinfo=UTC)
        events = [
            _make_event(op="I", columns={"id": 1, "name": "Alice"}, position="0/100", timestamp=ts1),
            _make_event(op="I", columns={"id": 2, "name": "Bob"}, position="0/200", timestamp=ts2),
        ]
        table = self._make_raw_table(events)
        result = build_scd2_table(table, ["id"])
        # Each PK is independent — both should have valid_to = null
        assert result.column(SCD2_VALID_TO_COLUMN)[0].as_py() is None
        assert result.column(SCD2_VALID_TO_COLUMN)[1].as_py() is None

    def test_empty_pk_columns_all_null_valid_to(self):
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        events = [
            _make_event(op="I", columns={"id": 1}, timestamp=ts),
            _make_event(op="U", columns={"id": 1}, timestamp=ts),
        ]
        table = self._make_raw_table(events)
        result = build_scd2_table(table, [])
        # Can't determine groups without PKs, all rows get valid_to = null
        assert result.column(SCD2_VALID_TO_COLUMN).to_pylist() == [None, None]

    def test_valid_from_equals_cdc_timestamp(self):
        ts = datetime(2026, 3, 15, 10, 30, 0, tzinfo=UTC)
        table = self._make_raw_table([_make_event(timestamp=ts)])
        result = build_scd2_table(table, ["id"])
        assert result.column(SCD2_VALID_FROM_COLUMN)[0].as_py() == ts
        assert result.column(CDC_TIMESTAMP_COLUMN)[0].as_py() == ts


class TestEnrichDeleteRows:
    def _make_raw_table(self, events):
        batcher = ChangeEventBatcher()
        for ev in events:
            batcher.add(ev)
        return batcher.flush()["users"]

    def test_no_deletes_returns_unchanged(self):
        table = self._make_raw_table([_make_event(op="I", columns={"id": 1, "name": "Alice"})])
        result = enrich_delete_rows(table, ["id"])
        assert result.num_rows == 1
        assert result.column("name")[0].as_py() == "Alice"

    def test_delete_after_insert_same_batch_fills_data(self):
        events = [
            _make_event(op="I", columns={"id": 1, "name": "Alice"}),
            _make_event(op="D", columns={"id": 1}),
        ]
        table = self._make_raw_table(events)
        result = enrich_delete_rows(table, ["id"])
        assert result.column("name")[1].as_py() == "Alice"
        assert result.column(CDC_OP_COLUMN)[1].as_py() == "D"
        assert result.column(DELETED_COLUMN)[1].as_py() is True

    def test_delete_after_update_uses_update_data(self):
        events = [
            _make_event(op="I", columns={"id": 1, "name": "Alice"}),
            _make_event(op="U", columns={"id": 1, "name": "Bob"}),
            _make_event(op="D", columns={"id": 1}),
        ]
        table = self._make_raw_table(events)
        result = enrich_delete_rows(table, ["id"])
        assert result.column("name")[2].as_py() == "Bob"

    def test_delete_without_prior_event_uses_existing_rows(self):
        table = self._make_raw_table([_make_event(op="D", columns={"id": 1})])
        existing = self._make_raw_table([_make_event(op="I", columns={"id": 1, "name": "Alice"})])
        result = enrich_delete_rows(table, ["id"], existing_rows=existing)
        assert result.column("name")[0].as_py() == "Alice"
        assert result.column(CDC_OP_COLUMN)[0].as_py() == "D"

    def test_existing_rows_do_not_overwrite_batch_data(self):
        events = [
            _make_event(op="U", columns={"id": 1, "name": "Bob"}),
            _make_event(op="D", columns={"id": 1}),
        ]
        table = self._make_raw_table(events)
        existing = self._make_raw_table([_make_event(op="I", columns={"id": 1, "name": "OldAlice"})])
        result = enrich_delete_rows(table, ["id"], existing_rows=existing)
        # Batch-internal UPDATE "Bob" takes priority over existing row "OldAlice"
        assert result.column("name")[1].as_py() == "Bob"

    def test_metadata_columns_preserved_from_delete_event(self):
        ts_insert = datetime(2025, 1, 1, tzinfo=UTC)
        ts_delete = datetime(2025, 6, 1, tzinfo=UTC)
        events = [
            _make_event(op="I", columns={"id": 1, "name": "Alice"}, timestamp=ts_insert),
            _make_event(op="D", columns={"id": 1}, timestamp=ts_delete),
        ]
        table = self._make_raw_table(events)
        result = enrich_delete_rows(table, ["id"])
        # Timestamp should come from the DELETE event, not the INSERT
        assert result.column(CDC_TIMESTAMP_COLUMN)[1].as_py() == ts_delete
        assert result.column(DELETED_AT_COLUMN)[1].as_py() == ts_delete
        assert result.column(DELETED_COLUMN)[1].as_py() is True

    def test_empty_pk_columns_returns_unchanged(self):
        table = self._make_raw_table([_make_event(op="D", columns={"id": 1})])
        result = enrich_delete_rows(table, [])
        assert result.num_rows == 1

    def test_different_pks_enriched_independently(self):
        events = [
            _make_event(op="I", columns={"id": 1, "name": "Alice"}),
            _make_event(op="I", columns={"id": 2, "name": "Bob"}),
            _make_event(op="D", columns={"id": 1}),
        ]
        table = self._make_raw_table(events)
        result = enrich_delete_rows(table, ["id"])
        # id=1 DELETE should be enriched with Alice; id=2 INSERT untouched
        assert result.column("name")[2].as_py() == "Alice"
        assert result.column("name")[1].as_py() == "Bob"
