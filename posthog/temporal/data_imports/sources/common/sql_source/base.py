from collections.abc import Callable
from typing import Any, Generic, Optional, Protocol, TypeVar

from sshtunnel import BaseSSHTunnelForwarderError

from posthog.exceptions_capture import capture_exception
from posthog.temporal.data_imports.pipelines.pipeline.typings import SourceInputs, SourceResponse
from posthog.temporal.data_imports.sources.common.base import SimpleSource
from posthog.temporal.data_imports.sources.common.config import Config
from posthog.temporal.data_imports.sources.common.mixins import SSHTunnelMixin, ValidateDatabaseHostMixin
from posthog.temporal.data_imports.sources.common.schema import SourceSchema
from posthog.temporal.data_imports.sources.common.sql_source.typing import (
    ConnectionErrorMap,
    ExceptionHandler,
    ForeignKeyMapping,
    RowCountMapping,
    SchemaColumns,
)

from products.data_warehouse.backend.models.ssh_tunnel import SSHTunnelConfig
from products.data_warehouse.backend.types import IncrementalField, IncrementalFieldType


class SQLConfigProtocol(Protocol):
    """Protocol defining the common fields all SQL source configs must have."""

    host: str
    port: int
    user: str
    password: str
    database: str
    schema: str
    ssh_tunnel: SSHTunnelConfig | None


SQLConfigType = TypeVar("SQLConfigType", bound=Config)


class SQLSource(SimpleSource[SQLConfigType], SSHTunnelMixin, ValidateDatabaseHostMixin, Generic[SQLConfigType]):
    """Base class for SQL database sources (MySQL, Postgres, MSSQL, ClickHouse, etc.).

    Subclasses configure behavior by setting class attributes for the injected functions
    and optionally overriding hooks for DB-specific kwargs and enrichment.

    Required class attributes:
        source_display_name: Human-readable name for error messages (e.g. "MySQL")
        _schema_fetcher: staticmethod — fetches table/column metadata from the database.
            Called with (host, port, user, password, database, schema, names, **extra_schema_kwargs).
            Returns SchemaColumns: dict[table_name, list[(col_name, data_type, is_nullable)]].
        _incremental_filter: staticmethod — filters columns eligible for incremental sync.
            Called with (columns) -> list of (field_name, IncrementalFieldType, nullable).
        _source_creator: staticmethod — creates the pipeline source response.
            Called with (tunnel, user, password, database, schema, table_names,
            should_use_incremental_field, logger, incremental_field, incremental_field_type,
            db_incremental_field_last_value, **extra_source_kwargs).

    Optional hooks (override in subclasses as needed):
        _get_extra_schema_kwargs(config) -> dict
            Extra kwargs for _schema_fetcher beyond the standard connection args.
        _get_extra_source_kwargs(config, inputs) -> dict
            Extra kwargs for _source_creator beyond the standard args.
        _get_foreign_keys(host, port, config, names) -> ForeignKeyMapping
            Called inside the SSH tunnel during get_schemas() to enrich SourceSchema.foreign_keys.
        _get_row_counts(host, port, config, names) -> RowCountMapping
            Called inside the SSH tunnel during get_schemas() when with_counts=True.
        _get_connection_error_class() -> type[Exception] | None
            DB-specific error class whose message is checked against _get_connection_error_map().
        _get_connection_error_map() -> ConnectionErrorMap
            Error message substrings mapped to user-friendly messages.
        _get_extra_exception_handlers() -> list[(exc_class, handler)]
            Priority exception handlers checked before the generic handler in validate_credentials().
    """

    source_display_name: str

    _schema_fetcher: Callable[..., SchemaColumns]
    _incremental_filter: Callable[[list[tuple[str, str, bool]]], list[tuple[str, IncrementalFieldType, bool]]]
    _source_creator: Callable[..., SourceResponse]

    # -- Optional hooks (override in subclasses as needed) --

    def _get_extra_schema_kwargs(self, config: SQLConfigType) -> dict[str, Any]:
        """Extra kwargs to pass to _schema_fetcher beyond the standard connection args."""
        return {}

    def _get_extra_source_kwargs(self, config: SQLConfigType, inputs: SourceInputs) -> dict[str, Any]:
        """Extra kwargs to pass to _source_creator beyond the standard args."""
        return {}

    def _get_foreign_keys(
        self, host: str, port: int, config: SQLConfigType, names: list[str] | None
    ) -> ForeignKeyMapping:
        """Return foreign key data to enrich SourceSchema.foreign_keys.

        Called inside the SSH tunnel in get_schemas(). Override in subclasses that support FKs.
        """
        return {}

    def _get_row_counts(self, host: str, port: int, config: SQLConfigType, names: list[str] | None) -> RowCountMapping:
        """Return row counts to enrich SourceSchema.row_count.

        Called inside the SSH tunnel in get_schemas() only when with_counts=True.
        Override in subclasses that can efficiently provide row counts.
        """
        return {}

    def _get_connection_error_class(self) -> type[Exception] | None:
        """Return the DB-specific connection error class (e.g. psycopg.OperationalError).

        When validate_credentials() catches a generic Exception, it checks if the exception
        is an instance of this class and applies _get_connection_error_map() for user-friendly messages.
        Return None if no special error class handling is needed.
        """
        return None

    def _get_connection_error_map(self) -> ConnectionErrorMap:
        """Return a mapping of error message substrings to user-friendly messages."""
        return {}

    def _get_extra_exception_handlers(self) -> list[tuple[type[Exception], ExceptionHandler]]:
        """Return priority exception handlers for validate_credentials().

        Each entry is (exception_class, handler_fn). When validate_credentials() catches
        a generic Exception, these handlers are checked first (in order) before the
        _get_connection_error_class() logic. The first matching handler wins.

        Example:
            return [(SSLRequiredError, lambda e: (False, str(e)))]
        """
        return []

    # -- Common implementations --

    def _config(self, config: SQLConfigType) -> SQLConfigProtocol:
        """Cast config to the SQL protocol for type-safe attribute access."""
        return config  # type: ignore[return-value]

    def get_schemas(
        self, config: SQLConfigType, team_id: int, with_counts: bool = False, names: list[str] | None = None
    ) -> list[SourceSchema]:
        c = self._config(config)

        with self.with_ssh_tunnel(config) as (host, port):
            db_schemas = self._schema_fetcher(
                host=host,
                port=port,
                user=c.user,
                password=c.password,
                database=c.database,
                schema=c.schema,
                names=names,
                **self._get_extra_schema_kwargs(config),
            )
            foreign_keys = self._get_foreign_keys(host, port, config, names)
            row_counts = self._get_row_counts(host, port, config, names) if with_counts else {}

        schemas: list[SourceSchema] = []
        for table_name, columns in db_schemas.items():
            incremental_field_tuples = self._incremental_filter(columns)
            incremental_fields: list[IncrementalField] = [
                {
                    "label": field_name,
                    "type": field_type,
                    "field": field_name,
                    "field_type": field_type,
                    "nullable": nullable,
                }
                for field_name, field_type, nullable in incremental_field_tuples
            ]

            schemas.append(
                SourceSchema(
                    name=table_name,
                    supports_incremental=len(incremental_fields) > 0,
                    supports_append=len(incremental_fields) > 0,
                    incremental_fields=incremental_fields,
                    columns=columns,
                    foreign_keys=foreign_keys.get(table_name, []),
                    row_count=row_counts.get(table_name),
                )
            )

        return schemas

    def validate_credentials(
        self, config: SQLConfigType, team_id: int, schema_name: Optional[str] = None
    ) -> tuple[bool, str | None]:
        c = self._config(config)

        is_ssh_valid, ssh_valid_errors = self.ssh_tunnel_is_valid(config, team_id)
        if not is_ssh_valid:
            return is_ssh_valid, ssh_valid_errors

        valid_host, host_errors = self.is_database_host_valid(
            c.host, team_id, using_ssh_tunnel=c.ssh_tunnel.enabled if c.ssh_tunnel else False
        )
        if not valid_host:
            return valid_host, host_errors

        try:
            self.get_schemas(config, team_id, names=[schema_name] if schema_name else None)
        except BaseSSHTunnelForwarderError as e:
            return (
                False,
                e.value
                or f"Could not connect to {self.source_display_name} via the SSH tunnel. Please check all connection details are valid.",
            )
        except Exception as e:
            for exc_class, handler in self._get_extra_exception_handlers():
                if isinstance(e, exc_class):
                    return handler(e)

            error_class = self._get_connection_error_class()
            if error_class is not None and isinstance(e, error_class):
                error_msg = " ".join(str(n) for n in e.args)
                for key, value in self._get_connection_error_map().items():
                    if key in error_msg:
                        return False, value

            capture_exception(e)
            return (
                False,
                f"Could not connect to {self.source_display_name}. Please check all connection details are valid.",
            )

        return True, None

    def source_for_pipeline(self, config: SQLConfigType, inputs: SourceInputs) -> SourceResponse:
        c = self._config(config)
        ssh_tunnel = self.make_ssh_tunnel_func(config)

        return self._source_creator(
            tunnel=ssh_tunnel,
            user=c.user,
            password=c.password,
            database=c.database,
            schema=c.schema,
            table_names=[inputs.schema_name],
            should_use_incremental_field=inputs.should_use_incremental_field,
            logger=inputs.logger,
            incremental_field=inputs.incremental_field,
            incremental_field_type=inputs.incremental_field_type,
            db_incremental_field_last_value=inputs.db_incremental_field_last_value,
            **self._get_extra_source_kwargs(config, inputs),
        )
