from __future__ import annotations

import re
import math
import collections
from collections.abc import Callable, Iterator
from contextlib import _GeneratorContextManager
from typing import Any, Optional

import pyarrow as pa
from clickhouse_connect import get_client
from clickhouse_connect.driver.client import Client as ClickHouseClient
from clickhouse_connect.driver.exceptions import ClickHouseError
from dlt.common.normalizers.naming.snake_case import NamingConvention
from structlog.types import FilteringBoundLogger

from posthog.exceptions_capture import capture_exception
from posthog.temporal.data_imports.pipelines.helpers import incremental_type_to_initial_value
from posthog.temporal.data_imports.pipelines.pipeline.consts import DEFAULT_CHUNK_SIZE
from posthog.temporal.data_imports.pipelines.pipeline.typings import SourceResponse
from posthog.temporal.data_imports.pipelines.pipeline.utils import (
    DEFAULT_PARTITION_TARGET_SIZE_IN_BYTES,
    build_pyarrow_decimal_type,
)
from posthog.temporal.data_imports.sources.common.sql import Column, Table

from products.data_warehouse.backend.types import IncrementalFieldType, PartitionSettings

# ClickHouse default ports
CLICKHOUSE_HTTP_PORT = 8123
CLICKHOUSE_HTTPS_PORT = 8443

# Connect timeout for the HTTP client
CONNECT_TIMEOUT_SECONDS = 15
# Per-query timeout for metadata/discovery queries
METADATA_QUERY_TIMEOUT_SECONDS = 30
# Per-query timeout for the main data extraction query
DATA_QUERY_TIMEOUT_SECONDS = 60 * 60  # 1 hour


class ClickHouseConnectionError(Exception):
    """Raised when we cannot establish or use a ClickHouse connection."""

    pass


def _quote_identifier(identifier: str) -> str:
    """Quote a ClickHouse identifier with backticks.

    ClickHouse allows arbitrary identifiers when wrapped in backticks. We
    escape backticks inside the name and refuse identifiers containing
    null bytes — both of which would be unusable in any sane schema.
    """
    if "\x00" in identifier:
        raise ValueError(f"identifier contains null byte: {identifier!r}")
    escaped = identifier.replace("`", "``")
    return f"`{escaped}`"


def _qualified_table(database: str, table_name: str) -> str:
    return f"{_quote_identifier(database)}.{_quote_identifier(table_name)}"


def _get_client(
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    secure: bool,
    verify: bool,
    query_timeout: int = DATA_QUERY_TIMEOUT_SECONDS,
    settings: Optional[dict[str, Any]] = None,
) -> ClickHouseClient:
    """Create a ClickHouse HTTP client.

    Uses clickhouse-connect, which speaks the HTTP/HTTPS interface. This is
    firewall-friendly, easy to tunnel via SSH, and exposes a streaming Arrow
    reader that we use to read very large tables without buffering them in
    memory.
    """
    try:
        return get_client(
            host=host,
            port=port,
            database=database,
            username=user,
            password=password,
            secure=secure,
            verify=verify,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            send_receive_timeout=query_timeout,
            query_limit=0,  # we manage limits ourselves
            settings=settings or {},
            compress=True,
        )
    except ClickHouseError as e:
        raise ClickHouseConnectionError(str(e)) from e


def _strip_type_modifiers(type_name: str) -> tuple[str, bool]:
    """Strip Nullable(...) and LowCardinality(...) wrappers.

    Returns the inner type and whether the original type was Nullable.
    LowCardinality alone does not affect nullability, so we recursively
    unwrap it but never set the nullable flag for it.
    """
    nullable = False
    current = type_name.strip()

    while True:
        if current.startswith("Nullable(") and current.endswith(")"):
            nullable = True
            current = current[len("Nullable(") : -1].strip()
        elif current.startswith("LowCardinality(") and current.endswith(")"):
            current = current[len("LowCardinality(") : -1].strip()
        else:
            break

    return current, nullable


def filter_clickhouse_incremental_fields(
    columns: list[tuple[str, str, bool]],
) -> list[tuple[str, IncrementalFieldType, bool]]:
    """Return columns suitable for use as an incremental cursor.

    ClickHouse type names are case-sensitive in metadata responses (e.g.
    `DateTime64(6)`, `Int64`, `Date`). We unwrap Nullable/LowCardinality
    wrappers first and then match against the bare type.
    """
    results: list[tuple[str, IncrementalFieldType, bool]] = []
    for column_name, raw_type, nullable in columns:
        inner_type, _ = _strip_type_modifiers(raw_type)
        # DateTime, DateTime64, DateTime('UTC'), DateTime64(3, 'UTC'), ...
        if inner_type.startswith("DateTime"):
            results.append((column_name, IncrementalFieldType.Timestamp, nullable))
        elif inner_type in ("Date", "Date32"):
            results.append((column_name, IncrementalFieldType.Date, nullable))
        elif inner_type in (
            "Int8",
            "Int16",
            "Int32",
            "Int64",
            "Int128",
            "Int256",
            "UInt8",
            "UInt16",
            "UInt32",
            "UInt64",
            "UInt128",
            "UInt256",
        ):
            results.append((column_name, IncrementalFieldType.Integer, nullable))

    return results


def get_schemas(
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    secure: bool,
    verify: bool,
    names: list[str] | None = None,
) -> dict[str, list[tuple[str, str, bool]]]:
    """Discover columns for all tables in the given database.

    Uses `system.columns`, which gives us everything in one round trip.
    Note: ClickHouse columns expose the *original* type string, including
    Nullable/LowCardinality wrappers — we keep the wrappers and parse them
    later, so we can preserve nullability information.
    """
    client = _get_client(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        secure=secure,
        verify=verify,
        query_timeout=METADATA_QUERY_TIMEOUT_SECONDS,
    )

    try:
        params: dict[str, Any] = {"database": database}
        names_filter = ""
        if names:
            # clickhouse-connect formats tuples as `(a, b, c)`, which matches
            # ClickHouse's IN clause syntax. Lists would format as `[a, b, c]`
            # which is valid but less standard.
            params["names"] = tuple(names)
            names_filter = "AND table IN %(names)s"

        result = client.query(
            f"""
            SELECT table, name, type
            FROM system.columns
            WHERE database = %(database)s {names_filter}
            ORDER BY table ASC, position ASC
            """,
            parameters=params,
        )
    finally:
        client.close()

    schema_list: dict[str, list[tuple[str, str, bool]]] = collections.defaultdict(list)
    for row in result.result_rows:
        table_name, column_name, raw_type = row[0], row[1], row[2]
        _, nullable = _strip_type_modifiers(raw_type)
        schema_list[table_name].append((column_name, raw_type, nullable))

    return schema_list


def get_clickhouse_row_count(
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    secure: bool,
    verify: bool,
    names: list[str] | None = None,
) -> dict[str, int]:
    """Return total_rows per table from `system.tables`.

    For MergeTree-family tables this is essentially free — ClickHouse keeps
    a running counter in metadata. For other engines (Memory, Distributed,
    View, ...) `total_rows` may be NULL, in which case we omit the entry.
    """
    client = _get_client(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        secure=secure,
        verify=verify,
        query_timeout=METADATA_QUERY_TIMEOUT_SECONDS,
    )

    try:
        params: dict[str, Any] = {"database": database}
        names_filter = ""
        if names:
            params["names"] = tuple(names)
            names_filter = "AND name IN %(names)s"

        result = client.query(
            f"""
            SELECT name, total_rows
            FROM system.tables
            WHERE database = %(database)s {names_filter} AND total_rows IS NOT NULL
            """,
            parameters=params,
        )
    except ClickHouseError:
        return {}
    finally:
        client.close()

    return {row[0]: int(row[1]) for row in result.result_rows if row[1] is not None}


def get_connection_metadata(
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    secure: bool,
    verify: bool,
) -> dict[str, Any]:
    """Probe the server for version metadata.

    Used during onboarding to surface a sensible error if credentials are
    valid but the database doesn't exist, and to record server version on
    the source for future debugging.
    """
    client = _get_client(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        secure=secure,
        verify=verify,
        query_timeout=METADATA_QUERY_TIMEOUT_SECONDS,
    )

    try:
        result = client.query("SELECT version(), currentDatabase()")
        row = result.result_rows[0] if result.result_rows else (None, None)
        version = str(row[0]) if row[0] is not None else ""
        current_database = str(row[1]) if row[1] is not None else database

        return {
            "database": current_database,
            "version": version,
            "engine": "clickhouse",
        }
    finally:
        client.close()


# Regex helpers for parsing ClickHouse type strings.
_DECIMAL_RE = re.compile(r"^Decimal(?:32|64|128|256)?\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)$")
_DATETIME64_RE = re.compile(r"^DateTime64\(\s*(\d+)\s*(?:,\s*'([^']*)'\s*)?\)$")
_DATETIME_RE = re.compile(r"^DateTime(?:\(\s*'([^']*)'\s*\))?$")
_FIXED_STRING_RE = re.compile(r"^FixedString\(\s*\d+\s*\)$")
_ENUM_RE = re.compile(r"^Enum(?:8|16)\(.*\)$")


def _datetime_unit_for_precision(precision: int) -> str:
    if precision <= 0:
        return "s"
    if precision <= 3:
        return "ms"
    if precision <= 6:
        return "us"
    return "ns"


class ClickHouseColumn(Column):
    """Implementation of the `Column` protocol for a ClickHouse source.

    Attributes:
        name: The column's name.
        data_type: The original ClickHouse type string, possibly wrapped in
            `Nullable(...)` and/or `LowCardinality(...)`.
        nullable: Whether the column is nullable. Derived from the
            `Nullable(...)` wrapper.
    """

    def __init__(self, name: str, data_type: str, nullable: bool) -> None:
        self.name = name
        self.data_type = data_type
        self.nullable = nullable

    def to_arrow_field(self) -> pa.Field[pa.DataType]:
        inner, _ = _strip_type_modifiers(self.data_type)
        arrow_type = self._inner_to_arrow_type(inner)
        return pa.field(self.name, arrow_type, nullable=self.nullable)

    @classmethod
    def _inner_to_arrow_type(cls, inner: str) -> pa.DataType:
        # Integer types
        match inner:
            case "Int8":
                return pa.int8()
            case "Int16":
                return pa.int16()
            case "Int32":
                return pa.int32()
            case "Int64":
                return pa.int64()
            case "UInt8":
                return pa.uint8()
            case "UInt16":
                return pa.uint16()
            case "UInt32":
                return pa.uint32()
            case "UInt64":
                return pa.uint64()
            case "Float32":
                return pa.float32()
            case "Float64":
                return pa.float64()
            case "Bool":
                return pa.bool_()
            case "String":
                return pa.string()
            case "UUID":
                return pa.string()
            case "Date":
                return pa.date32()
            case "Date32":
                return pa.date32()
            case "IPv4" | "IPv6":
                return pa.string()
            # Wide integers we cannot represent natively in Arrow — fall back to
            # string so we don't silently truncate.
            case "Int128" | "Int256" | "UInt128" | "UInt256":
                return pa.string()

        # DateTime / DateTime('UTC')
        match_dt = _DATETIME_RE.match(inner)
        if match_dt is not None:
            tz = match_dt.group(1) or None
            return pa.timestamp("s", tz=tz)

        # DateTime64(precision[, timezone])
        match_dt64 = _DATETIME64_RE.match(inner)
        if match_dt64 is not None:
            precision = int(match_dt64.group(1))
            tz = match_dt64.group(2) or None
            return pa.timestamp(_datetime_unit_for_precision(precision), tz=tz)

        # Decimal[32|64|128|256](p[, s])
        match_dec = _DECIMAL_RE.match(inner)
        if match_dec is not None:
            precision = int(match_dec.group(1))
            scale = int(match_dec.group(2)) if match_dec.group(2) is not None else 0
            return build_pyarrow_decimal_type(precision, scale)

        # FixedString(N) — bytes-like, but stored as string for portability
        if _FIXED_STRING_RE.match(inner):
            return pa.string()

        # Enum8(...) / Enum16(...) — surface labels as strings
        if _ENUM_RE.match(inner):
            return pa.string()

        # Composite types — Array, Map, Tuple, Nested, JSON, Object — are
        # serialized to a JSON string. We could be smarter about Array of
        # primitives in the future.
        if (
            inner.startswith("Array(")
            or inner.startswith("Map(")
            or inner.startswith("Tuple(")
            or inner.startswith("Nested(")
            or inner.startswith("Variant(")
            or inner.startswith("Dynamic")
            or inner.startswith("JSON")
            or inner.startswith("Object(")
        ):
            return pa.string()

        # Anything we don't recognise is safest as a string.
        return pa.string()


def _is_view_engine(engine: str | None) -> bool:
    if not engine:
        return False
    return engine in ("View", "MaterializedView", "LiveView", "WindowView")


def _is_materialized_view_engine(engine: str | None) -> bool:
    return engine == "MaterializedView"


def _get_table(client: ClickHouseClient, database: str, table_name: str) -> Table[ClickHouseColumn]:
    """Read columns + table type for a single table from system tables."""
    cols_result = client.query(
        """
        SELECT name, type
        FROM system.columns
        WHERE database = %(database)s AND table = %(table)s
        ORDER BY position ASC
        """,
        parameters={"database": database, "table": table_name},
    )

    columns: list[ClickHouseColumn] = []
    for name, raw_type in cols_result.result_rows:
        _, nullable = _strip_type_modifiers(raw_type)
        columns.append(ClickHouseColumn(name=name, data_type=raw_type, nullable=nullable))

    if not columns:
        raise ValueError(f"Table {database}.{table_name} not found or has no columns")

    engine_result = client.query(
        "SELECT engine FROM system.tables WHERE database = %(database)s AND name = %(table)s",
        parameters={"database": database, "table": table_name},
    )
    engine = engine_result.result_rows[0][0] if engine_result.result_rows else None

    table_type: str = "table"
    if _is_materialized_view_engine(engine):
        table_type = "materialized_view"
    elif _is_view_engine(engine):
        table_type = "view"

    return Table(name=table_name, parents=(database,), columns=columns, type=table_type)  # type: ignore[arg-type]


def _get_primary_keys(client: ClickHouseClient, database: str, table_name: str) -> list[str] | None:
    """Return the columns of the table's sorting key.

    ClickHouse's primary key is by definition a prefix of the sorting key,
    and is the closest analog to a unique key — though it is *not*
    necessarily unique. Callers must be prepared to handle duplicates.
    """
    result = client.query(
        """
        SELECT name
        FROM system.columns
        WHERE database = %(database)s AND table = %(table)s AND is_in_sorting_key = 1
        ORDER BY position ASC
        """,
        parameters={"database": database, "table": table_name},
    )
    keys = [row[0] for row in result.result_rows]
    return keys if keys else None


def _has_duplicate_primary_keys(
    client: ClickHouseClient,
    database: str,
    table_name: str,
    primary_keys: list[str] | None,
    logger: FilteringBoundLogger,
) -> bool:
    """Check whether the sorting key has duplicate combinations.

    For ClickHouse the sorting key is rarely unique, so we always run this
    check before incrementally syncing — see SourceResponse docs.
    """
    if not primary_keys:
        return False

    quoted_keys = ", ".join(_quote_identifier(k) for k in primary_keys)
    query = f"SELECT 1 FROM {_qualified_table(database, table_name)} GROUP BY {quoted_keys} HAVING count() > 1 LIMIT 1"
    try:
        result = client.query(query)
        return len(result.result_rows) > 0
    except ClickHouseError as e:
        logger.debug(f"_has_duplicate_primary_keys: failed to check duplicates: {e}")
        capture_exception(e)
        return False


def _get_partition_settings(
    client: ClickHouseClient, database: str, table_name: str, logger: FilteringBoundLogger
) -> PartitionSettings | None:
    """Compute partition settings using `system.tables.total_bytes`.

    ClickHouse maintains compressed and uncompressed sizes per table — we
    use total_bytes (compressed on disk) as a rough proxy for memory cost
    on the pipeline side. For non-MergeTree engines `total_bytes` may be
    NULL, in which case we return None and the pipeline falls back to its
    default partitioning.
    """
    try:
        result = client.query(
            """
            SELECT total_rows, total_bytes
            FROM system.tables
            WHERE database = %(database)s AND name = %(table)s
            """,
            parameters={"database": database, "table": table_name},
        )
    except ClickHouseError as e:
        capture_exception(e)
        logger.debug(f"_get_partition_settings: failed: {e}")
        return None

    if not result.result_rows:
        return None

    total_rows, total_bytes = result.result_rows[0]
    if total_rows is None or total_bytes is None or total_rows == 0 or total_bytes == 0:
        return None

    bytes_per_row = total_bytes / total_rows
    if bytes_per_row <= 0:
        return None

    partition_size = max(1, int(round(DEFAULT_PARTITION_TARGET_SIZE_IN_BYTES / bytes_per_row)))
    partition_count = max(1, math.floor(total_rows / partition_size))

    logger.debug(
        f"_get_partition_settings: total_rows={total_rows} total_bytes={total_bytes} "
        f"partition_size={partition_size} partition_count={partition_count}"
    )
    return PartitionSettings(partition_count=partition_count, partition_size=partition_size)


def _build_query(
    *,
    database: str,
    table_name: str,
    should_use_incremental_field: bool,
    incremental_field: Optional[str],
    incremental_field_type: Optional[IncrementalFieldType],
) -> tuple[str, dict[str, Any]]:
    """Build the data extraction query.

    Returns the SQL plus a parameter dict for clickhouse-connect's
    parameterized query API. We never interpolate the incremental cursor
    value directly — only identifiers (which are validated) end up in the
    SQL string.
    """
    qualified = _qualified_table(database, table_name)

    if not should_use_incremental_field:
        return f"SELECT * FROM {qualified}", {}

    if incremental_field is None or incremental_field_type is None:
        raise ValueError("incremental_field and incremental_field_type can't be None")

    quoted_field = _quote_identifier(incremental_field)
    return (
        f"SELECT * FROM {qualified} WHERE {quoted_field} > %(last_value)s ORDER BY {quoted_field} ASC",
        {},
    )


def _query_settings(chunk_size: int) -> dict[str, Any]:
    """ClickHouse server-side settings applied to every data query.

    These tune the streaming Arrow output and prevent runaway resource use
    on the source side. They are intentionally conservative — operators
    can override per-source via chunk_size_override on the schema.
    """
    return {
        # Stream Arrow record batches in chunks of `chunk_size` rows. This is
        # the per-batch row limit on the source side and bounds memory.
        "max_block_size": chunk_size,
        # Make Arrow output use real String columns instead of binary buffers,
        # which keeps the resulting RecordBatches readable by Delta Lake.
        "output_format_arrow_string_as_string": 1,
        # Materialize LowCardinality columns into their underlying type, so the
        # PyArrow schema we generate matches what we receive.
        "output_format_arrow_low_cardinality_as_dictionary": 0,
        # Cap query execution time to avoid hanging the worker on a runaway
        # source-side query.
        "max_execution_time": DATA_QUERY_TIMEOUT_SECONDS,
    }


def clickhouse_source(
    *,
    tunnel: Callable[[], _GeneratorContextManager[tuple[str, int]]],
    user: str,
    password: str,
    database: str,
    secure: bool,
    verify: bool,
    table_names: list[str],
    should_use_incremental_field: bool,
    logger: FilteringBoundLogger,
    db_incremental_field_last_value: Optional[Any],
    chunk_size_override: Optional[int] = None,
    incremental_field: Optional[str] = None,
    incremental_field_type: Optional[IncrementalFieldType] = None,
) -> SourceResponse:
    """Build a SourceResponse that pulls a single ClickHouse table.

    Streams the data via Arrow batches so we never materialize the whole
    table in memory. Each yielded `pa.Table` is one Arrow record batch.
    """
    table_name = table_names[0]
    if not table_name:
        raise ValueError("Table name is missing")

    chunk_size = chunk_size_override if chunk_size_override is not None else DEFAULT_CHUNK_SIZE

    with tunnel() as (host, port):
        client = _get_client(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            secure=secure,
            verify=verify,
            query_timeout=METADATA_QUERY_TIMEOUT_SECONDS,
        )

        try:
            logger.debug(f"Discovering table {database}.{table_name}")
            table = _get_table(client, database, table_name)
            logger.debug(f"Source schema: {table.to_arrow_schema()}")

            primary_keys = _get_primary_keys(client, database, table_name)
            if primary_keys:
                logger.debug(f"Found primary keys (sorting key): {primary_keys}")

            row_counts = get_clickhouse_row_count(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                secure=secure,
                verify=verify,
                names=[table_name],
            )
            rows_to_sync = row_counts.get(table_name, 0)

            partition_settings = (
                _get_partition_settings(client, database, table_name, logger) if should_use_incremental_field else None
            )

            has_duplicate_primary_keys = False
            if should_use_incremental_field and primary_keys:
                has_duplicate_primary_keys = _has_duplicate_primary_keys(
                    client, database, table_name, primary_keys, logger
                )
        finally:
            client.close()

    def get_rows() -> Iterator[Any]:
        # Open a fresh tunnel + client for the streaming read so the
        # connection used for discovery isn't held open longer than needed.
        with tunnel() as (stream_host, stream_port):
            stream_client = _get_client(
                host=stream_host,
                port=stream_port,
                database=database,
                user=user,
                password=password,
                secure=secure,
                verify=verify,
                query_timeout=DATA_QUERY_TIMEOUT_SECONDS,
                settings=_query_settings(chunk_size),
            )

            try:
                query, _ = _build_query(
                    database=database,
                    table_name=table_name,
                    should_use_incremental_field=should_use_incremental_field,
                    incremental_field=incremental_field,
                    incremental_field_type=incremental_field_type,
                )

                parameters: dict[str, Any] = {}
                if should_use_incremental_field:
                    last_value = db_incremental_field_last_value
                    if last_value is None and incremental_field_type is not None:
                        last_value = incremental_type_to_initial_value(incremental_field_type)
                    parameters["last_value"] = last_value

                logger.debug(f"ClickHouse query: {query}")

                # query_arrow_stream yields a StreamContext of pyarrow.Table
                # chunks — one per ClickHouse block, capped by max_block_size.
                with stream_client.query_arrow_stream(query, parameters=parameters) as stream:
                    for chunk in stream:
                        if chunk.num_rows == 0:
                            continue
                        yield chunk
            finally:
                stream_client.close()

    name = NamingConvention().normalize_identifier(table_name)

    return SourceResponse(
        name=name,
        items=get_rows,
        primary_keys=primary_keys,
        partition_count=partition_settings.partition_count if partition_settings else None,
        partition_size=partition_settings.partition_size if partition_settings else None,
        rows_to_sync=rows_to_sync,
        has_duplicate_primary_keys=has_duplicate_primary_keys,
    )
