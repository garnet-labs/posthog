import pytest
from unittest.mock import MagicMock, patch

import pyarrow as pa

from posthog.temporal.data_imports.sources.clickhouse.clickhouse import (
    ClickHouseColumn,
    _build_query,
    _qualified_table,
    _quote_identifier,
    _strip_type_modifiers,
    filter_clickhouse_incremental_fields,
)
from posthog.temporal.data_imports.sources.clickhouse.source import ClickHouseSource

from products.data_warehouse.backend.types import IncrementalFieldType


class TestQuoteIdentifier:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("users", "`users`"),
            ("user_id", "`user_id`"),
            ("CamelCase", "`CamelCase`"),
            ("with space", "`with space`"),
            ("with`backtick", "`with``backtick`"),
            ("123starts_with_digit", "`123starts_with_digit`"),
        ],
    )
    def test_quotes_and_escapes(self, name, expected):
        assert _quote_identifier(name) == expected

    def test_rejects_null_byte(self):
        with pytest.raises(ValueError, match="null byte"):
            _quote_identifier("bad\x00name")


class TestQualifiedTable:
    def test_qualifies_with_database(self):
        assert _qualified_table("default", "events") == "`default`.`events`"

    def test_quotes_special_chars(self):
        assert _qualified_table("my-db", "my table") == "`my-db`.`my table`"


class TestStripTypeModifiers:
    @pytest.mark.parametrize(
        "raw,expected_inner,expected_nullable",
        [
            ("Int64", "Int64", False),
            ("Nullable(Int64)", "Int64", True),
            ("LowCardinality(String)", "String", False),
            ("Nullable(LowCardinality(String))", "String", True),
            ("LowCardinality(Nullable(String))", "String", True),
            ("Nullable(DateTime64(6, 'UTC'))", "DateTime64(6, 'UTC')", True),
            ("Decimal(18, 4)", "Decimal(18, 4)", False),
            ("  Nullable(Int32)  ", "Int32", True),
        ],
    )
    def test_strips(self, raw, expected_inner, expected_nullable):
        inner, nullable = _strip_type_modifiers(raw)
        assert inner == expected_inner
        assert nullable is expected_nullable


class TestFilterClickHouseIncrementalFields:
    @pytest.mark.parametrize(
        "type_name,expected_type",
        [
            ("Int8", IncrementalFieldType.Integer),
            ("Int16", IncrementalFieldType.Integer),
            ("Int32", IncrementalFieldType.Integer),
            ("Int64", IncrementalFieldType.Integer),
            ("Int128", IncrementalFieldType.Integer),
            ("Int256", IncrementalFieldType.Integer),
            ("UInt8", IncrementalFieldType.Integer),
            ("UInt16", IncrementalFieldType.Integer),
            ("UInt32", IncrementalFieldType.Integer),
            ("UInt64", IncrementalFieldType.Integer),
            ("Date", IncrementalFieldType.Date),
            ("Date32", IncrementalFieldType.Date),
            ("DateTime", IncrementalFieldType.Timestamp),
            ("DateTime('UTC')", IncrementalFieldType.Timestamp),
            ("DateTime64(3)", IncrementalFieldType.Timestamp),
            ("DateTime64(6, 'UTC')", IncrementalFieldType.Timestamp),
            ("Nullable(Int64)", IncrementalFieldType.Integer),
            ("Nullable(DateTime)", IncrementalFieldType.Timestamp),
            ("LowCardinality(Int32)", IncrementalFieldType.Integer),
        ],
    )
    def test_supported_types(self, type_name, expected_type):
        result = filter_clickhouse_incremental_fields([("col", type_name, False)])
        assert result == [("col", expected_type, False)]

    @pytest.mark.parametrize(
        "type_name",
        [
            "String",
            "FixedString(8)",
            "Float32",
            "Float64",
            "Decimal(18, 4)",
            "UUID",
            "Bool",
            "Array(Int64)",
            "Map(String, Int64)",
            "Tuple(Int64, String)",
            "Enum8('a' = 1, 'b' = 2)",
            "IPv4",
            "JSON",
        ],
    )
    def test_unsupported_types_excluded(self, type_name):
        result = filter_clickhouse_incremental_fields([("col", type_name, False)])
        assert result == []

    def test_preserves_nullable_flag(self):
        result = filter_clickhouse_incremental_fields([("col", "Nullable(Int64)", True)])
        assert result == [("col", IncrementalFieldType.Integer, True)]

    def test_multiple_columns(self):
        columns = [
            ("id", "UInt64", False),
            ("name", "String", False),
            ("created_at", "DateTime64(6, 'UTC')", True),
            ("amount", "Decimal(18, 4)", False),
            ("event_date", "Date", False),
        ]
        result = filter_clickhouse_incremental_fields(columns)
        assert result == [
            ("id", IncrementalFieldType.Integer, False),
            ("created_at", IncrementalFieldType.Timestamp, True),
            ("event_date", IncrementalFieldType.Date, False),
        ]

    def test_empty_list(self):
        assert filter_clickhouse_incremental_fields([]) == []


class TestBuildQuery:
    def test_full_refresh(self):
        query, params = _build_query(
            database="default",
            table_name="events",
            should_use_incremental_field=False,
            incremental_field=None,
            incremental_field_type=None,
        )
        assert query == "SELECT * FROM `default`.`events`"
        assert params == {}

    def test_incremental(self):
        query, params = _build_query(
            database="default",
            table_name="events",
            should_use_incremental_field=True,
            incremental_field="created_at",
            incremental_field_type=IncrementalFieldType.Timestamp,
        )
        assert "SELECT * FROM `default`.`events`" in query
        assert "WHERE `created_at` > %(last_value)s" in query
        assert "ORDER BY `created_at` ASC" in query
        assert params == {}

    def test_incremental_quotes_field_with_special_chars(self):
        query, _ = _build_query(
            database="my-db",
            table_name="weird table",
            should_use_incremental_field=True,
            incremental_field="event time",
            incremental_field_type=IncrementalFieldType.Timestamp,
        )
        assert "`my-db`.`weird table`" in query
        assert "`event time`" in query

    def test_incremental_raises_without_field(self):
        with pytest.raises(ValueError, match="incremental_field and incremental_field_type can't be None"):
            _build_query(
                database="default",
                table_name="events",
                should_use_incremental_field=True,
                incremental_field=None,
                incremental_field_type=None,
            )


class TestClickHouseColumnToArrowField:
    @pytest.mark.parametrize(
        "data_type,expected_arrow_type",
        [
            ("Int8", pa.int8()),
            ("Int16", pa.int16()),
            ("Int32", pa.int32()),
            ("Int64", pa.int64()),
            ("UInt8", pa.uint8()),
            ("UInt16", pa.uint16()),
            ("UInt32", pa.uint32()),
            ("UInt64", pa.uint64()),
            ("Float32", pa.float32()),
            ("Float64", pa.float64()),
            ("Bool", pa.bool_()),
            ("String", pa.string()),
            ("UUID", pa.string()),
            ("Date", pa.date32()),
            ("Date32", pa.date32()),
            ("IPv4", pa.string()),
            ("IPv6", pa.string()),
            ("Int128", pa.string()),
            ("Int256", pa.string()),
            ("UInt128", pa.string()),
            ("UInt256", pa.string()),
            ("FixedString(16)", pa.string()),
            ("Enum8('a' = 1, 'b' = 2)", pa.string()),
            ("Enum16('long_label' = 1)", pa.string()),
            ("Array(Int64)", pa.string()),
            ("Map(String, Int64)", pa.string()),
            ("Tuple(Int64, String)", pa.string()),
            ("JSON", pa.string()),
        ],
    )
    def test_simple_type_mappings(self, data_type, expected_arrow_type):
        col = ClickHouseColumn("test_col", data_type, nullable=True)
        field = col.to_arrow_field()
        assert field.type == expected_arrow_type
        assert field.name == "test_col"
        assert field.nullable is True

    def test_datetime_no_tz(self):
        col = ClickHouseColumn("ts", "DateTime", nullable=False)
        field = col.to_arrow_field()
        assert field.type == pa.timestamp("s")

    def test_datetime_with_tz(self):
        col = ClickHouseColumn("ts", "DateTime('UTC')", nullable=False)
        field = col.to_arrow_field()
        assert field.type == pa.timestamp("s", tz="UTC")

    @pytest.mark.parametrize(
        "data_type,expected_unit",
        [
            ("DateTime64(0)", "s"),
            ("DateTime64(3)", "ms"),
            ("DateTime64(6)", "us"),
            ("DateTime64(9)", "ns"),
        ],
    )
    def test_datetime64_precision(self, data_type, expected_unit):
        col = ClickHouseColumn("ts", data_type, nullable=False)
        field = col.to_arrow_field()
        assert field.type == pa.timestamp(expected_unit)

    def test_datetime64_with_tz(self):
        col = ClickHouseColumn("ts", "DateTime64(6, 'America/New_York')", nullable=False)
        field = col.to_arrow_field()
        assert field.type == pa.timestamp("us", tz="America/New_York")

    @pytest.mark.parametrize(
        "data_type",
        [
            "Decimal(10, 2)",
            "Decimal32(4)",
            "Decimal64(8)",
            "Decimal128(20)",
        ],
    )
    def test_decimal_types(self, data_type):
        col = ClickHouseColumn("amt", data_type, nullable=False)
        field = col.to_arrow_field()
        assert isinstance(field.type, (pa.Decimal128Type, pa.Decimal256Type))

    def test_nullable_wrapper(self):
        col = ClickHouseColumn("id", "Nullable(Int64)", nullable=True)
        field = col.to_arrow_field()
        assert field.type == pa.int64()
        assert field.nullable is True

    def test_low_cardinality_wrapper(self):
        col = ClickHouseColumn("name", "LowCardinality(String)", nullable=False)
        field = col.to_arrow_field()
        assert field.type == pa.string()
        assert field.nullable is False

    def test_nullable_low_cardinality(self):
        col = ClickHouseColumn("name", "LowCardinality(Nullable(String))", nullable=True)
        field = col.to_arrow_field()
        assert field.type == pa.string()
        assert field.nullable is True

    def test_unknown_type_maps_to_string(self):
        col = ClickHouseColumn("mystery", "AggregateFunction(uniq, UInt64)", nullable=True)
        field = col.to_arrow_field()
        assert field.type == pa.string()


class TestClickHouseSourceConfig:
    @pytest.fixture
    def source(self):
        return ClickHouseSource()

    def test_source_type(self, source):
        from products.data_warehouse.backend.types import ExternalDataSourceType

        assert source.source_type == ExternalDataSourceType.CLICKHOUSE

    def test_source_config_fields(self, source):
        config = source.get_source_config
        field_names = {f.name for f in config.fields}
        assert {"host", "port", "database", "user", "password", "secure", "verify", "ssh_tunnel"} <= field_names

    def test_non_retryable_errors_present(self, source):
        errors = source.get_non_retryable_errors()
        # A few key errors that should never be retried
        assert any("authentication" in k.lower() for k in errors)
        assert any("Code: 81" in k for k in errors)  # UNKNOWN_DATABASE


class TestClickHouseSourceNonRetryableErrors:
    @pytest.fixture
    def source(self):
        return ClickHouseSource()

    @pytest.mark.parametrize(
        "error_msg",
        [
            "Code: 516. DB::Exception: default: Authentication failed",
            "Code: 81. DB::Exception: Database `does_not_exist` doesn't exist",
            "Code: 60. DB::Exception: Table default.foo doesn't exist",
            "Could not resolve the ClickHouse host",
            "Connection refused",
            "certificate verify failed",
        ],
    )
    def test_permanent_errors_are_non_retryable(self, source, error_msg):
        non_retryable = source.get_non_retryable_errors()
        is_non_retryable = any(pattern in error_msg for pattern in non_retryable)
        assert is_non_retryable, f"Permanent error should be non-retryable: {error_msg}"

    @pytest.mark.parametrize(
        "error_msg",
        [
            "Code: 159. DB::Exception: Timeout exceeded",  # query timeout — could be retried
            "Code: 999. DB::Exception: Keeper exception",  # transient zookeeper-style errors
            "Code: 209. DB::Exception: Socket timeout",
        ],
    )
    def test_transient_errors_are_retryable(self, source, error_msg):
        non_retryable = source.get_non_retryable_errors()
        is_non_retryable = any(pattern in error_msg for pattern in non_retryable)
        assert not is_non_retryable, f"Transient error should be retryable: {error_msg}"


class TestTranslateError:
    def test_translates_known_errors(self):
        msg = "Code: 516. DB::Exception: Authentication failed for user 'default'"
        assert ClickHouseSource._translate_error(msg) == "Invalid user or password"

    def test_translates_unknown_database(self):
        msg = "Code: 81. DB::Exception: Database `nonexistent` doesn't exist"
        assert ClickHouseSource._translate_error(msg) == "Database does not exist"

    def test_returns_none_for_unrecognised_error(self):
        assert ClickHouseSource._translate_error("Some random error") is None


class TestGetSchemas:
    """Tests `get_schemas` with a fully mocked ClickHouse client."""

    def _make_mock_client(self, rows):
        client = MagicMock()
        result = MagicMock()
        result.result_rows = rows
        client.query.return_value = result
        return client

    def test_groups_columns_by_table(self):
        from posthog.temporal.data_imports.sources.clickhouse import clickhouse as ch_module

        rows = [
            ("events", "id", "UInt64"),
            ("events", "created_at", "DateTime64(6, 'UTC')"),
            ("events", "name", "Nullable(String)"),
            ("users", "id", "UInt64"),
            ("users", "email", "String"),
        ]
        mock_client = self._make_mock_client(rows)

        with patch.object(ch_module, "_get_client", return_value=mock_client):
            schemas = ch_module.get_schemas(
                host="localhost",
                port=8443,
                database="default",
                user="default",
                password="",
                secure=True,
                verify=True,
            )

        assert set(schemas.keys()) == {"events", "users"}
        assert len(schemas["events"]) == 3
        # Nullable detection
        events_cols = {c[0]: (c[1], c[2]) for c in schemas["events"]}
        assert events_cols["id"] == ("UInt64", False)
        assert events_cols["name"] == ("Nullable(String)", True)


class TestSourceClassValidateCredentials:
    """High-level checks on validate_credentials error mapping."""

    def test_returns_error_when_clickhouse_connection_fails(self):
        from posthog.temporal.data_imports.sources.clickhouse import source as source_module
        from posthog.temporal.data_imports.sources.clickhouse.clickhouse import ClickHouseConnectionError

        source = source_module.ClickHouseSource()

        config = MagicMock()
        config.host = "play.clickhouse.com"
        config.ssh_tunnel = None

        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(True, None)):
                with patch.object(
                    source,
                    "get_schemas",
                    side_effect=ClickHouseConnectionError("Code: 516. Authentication failed"),
                ):
                    valid, msg = source.validate_credentials(config, team_id=1)

        assert valid is False
        assert msg == "Invalid user or password"

    def test_returns_generic_message_for_unknown_error(self):
        from posthog.temporal.data_imports.sources.clickhouse import source as source_module
        from posthog.temporal.data_imports.sources.clickhouse.clickhouse import ClickHouseConnectionError

        source = source_module.ClickHouseSource()

        config = MagicMock()
        config.host = "play.clickhouse.com"
        config.ssh_tunnel = None

        with patch.object(source, "ssh_tunnel_is_valid", return_value=(True, None)):
            with patch.object(source, "is_database_host_valid", return_value=(True, None)):
                with patch.object(
                    source,
                    "get_schemas",
                    side_effect=ClickHouseConnectionError("something weird happened"),
                ):
                    valid, msg = source.validate_credentials(config, team_id=1)

        assert valid is False
        assert msg == "Could not connect to ClickHouse. Please check all connection details are valid."
