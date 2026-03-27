from typing import Any, cast

from psycopg import OperationalError

from posthog.schema import (
    ExternalDataSourceType as SchemaExternalDataSourceType,
    SourceConfig,
    SourceFieldInputConfig,
    SourceFieldInputConfigType,
    SourceFieldSSHTunnelConfig,
)

from posthog.temporal.data_imports.pipelines.pipeline.typings import SourceInputs
from posthog.temporal.data_imports.sources.common.base import FieldType
from posthog.temporal.data_imports.sources.common.registry import SourceRegistry
from posthog.temporal.data_imports.sources.common.sql_source import (
    ExceptionHandler,
    ForeignKeyMapping,
    RowCountMapping,
    SQLSource,
    SSLRequiredError,
)
from posthog.temporal.data_imports.sources.generated_configs import PostgresSourceConfig
from posthog.temporal.data_imports.sources.postgres.postgres import (
    SSL_REQUIRED_AFTER_DATE,
    filter_postgres_incremental_fields,
    get_connection_metadata as get_postgres_connection_metadata,
    get_foreign_keys as get_postgres_foreign_keys,
    get_postgres_row_count,
    get_schemas as get_postgres_schemas,
    postgres_source,
)

from products.data_warehouse.backend.types import ExternalDataSourceType

_POSTGRES_ERROR_MAP = {
    "password authentication failed for user": "Invalid user or password",
    "could not translate host name": "Could not connect to the host",
    "Is the server running on that host and accepting TCP/IP connections": "Could not connect to the host on the port given",
    'database "': "Database does not exist",
    "timeout expired": "Connection timed out. Does your database have our IP addresses allowed?",
    "SSL/TLS connection is required": "SSL/TLS connection is required but your database does not support it. Please enable SSL/TLS on your PostgreSQL server.",
}


@SourceRegistry.register
class PostgresSource(SQLSource[PostgresSourceConfig]):
    _schema_fetcher = staticmethod(get_postgres_schemas)
    _incremental_filter = staticmethod(filter_postgres_incremental_fields)
    _source_creator = staticmethod(postgres_source)

    def __init__(self, source_name: str = "Postgres"):
        super().__init__()
        self.source_name = source_name

    @property
    def source_display_name(self) -> str:
        return self.source_name

    @property
    def source_type(self) -> ExternalDataSourceType:
        return ExternalDataSourceType.POSTGRES

    @property
    def get_source_config(self) -> SourceConfig:
        return SourceConfig(
            name=SchemaExternalDataSourceType.POSTGRES,
            caption="Enter your Postgres credentials to automatically pull your Postgres data into the PostHog Data warehouse",
            iconPath="/static/services/postgres.png",
            docsUrl="https://posthog.com/docs/cdp/sources/postgres",
            fields=cast(
                list[FieldType],
                [
                    SourceFieldInputConfig(
                        name="connection_string",
                        label="Connection string (optional)",
                        type=SourceFieldInputConfigType.TEXT,
                        required=False,
                        placeholder="postgresql://user:password@localhost:5432/database",
                    ),
                    SourceFieldInputConfig(
                        name="host",
                        label="Host",
                        type=SourceFieldInputConfigType.TEXT,
                        required=True,
                        placeholder="localhost",
                    ),
                    SourceFieldInputConfig(
                        name="port",
                        label="Port",
                        type=SourceFieldInputConfigType.NUMBER,
                        required=True,
                        placeholder="5432",
                    ),
                    SourceFieldInputConfig(
                        name="database",
                        label="Database",
                        type=SourceFieldInputConfigType.TEXT,
                        required=True,
                        placeholder="postgres",
                    ),
                    SourceFieldInputConfig(
                        name="user",
                        label="User",
                        type=SourceFieldInputConfigType.TEXT,
                        required=True,
                        placeholder="postgres",
                    ),
                    SourceFieldInputConfig(
                        name="password",
                        label="Password",
                        type=SourceFieldInputConfigType.PASSWORD,
                        required=True,
                        placeholder="",
                    ),
                    SourceFieldInputConfig(
                        name="schema",
                        label="Schema",
                        type=SourceFieldInputConfigType.TEXT,
                        required=True,
                        placeholder="public",
                    ),
                    SourceFieldSSHTunnelConfig(name="ssh_tunnel", label="Use SSH tunnel?"),
                ],
            ),
            featured=True,
        )

    def get_non_retryable_errors(self) -> dict[str, str | None]:
        return {
            "NoSuchTableError": None,
            "is not permitted to log in": None,
            "Tenant or user not found connection to server": None,
            "FATAL: Tenant or user not found": None,
            "error received from server in SCRAM exchange: Wrong password": None,
            "could not translate host name": None,
            "timeout expired connection to server at": None,
            "password authentication failed for user": None,
            "No primary key defined for table": None,
            "failed: timeout expired": None,
            "SSL connection has been closed unexpectedly": None,
            "Address not in tenant allow_list": None,
            "FATAL: no such database": None,
            "does not exist": None,
            "timestamp too small": None,
            "QueryTimeoutException": None,
            "TemporaryFileSizeExceedsLimitException": None,
            "Name or service not known": None,
            "Network is unreachable": None,
            "InsufficientPrivilege": None,
            "Connection refused": None,
            "No route to host": None,
            "password authentication failed connection": None,
            "connection timeout expired": None,
            "SSLRequiredError": None,
            "SSL/TLS connection is required": None,
            "DiskFull": "Source database ran out of disk space. Free up disk space on your database server or add an index on your incremental field to reduce temp file usage.",
            "No space left on device": "Source database ran out of disk space. Free up disk space on your database server or add an index on your incremental field to reduce temp file usage.",
        }

    def _get_connection_error_class(self) -> type[Exception] | None:
        return OperationalError

    def _get_connection_error_map(self) -> dict[str, str]:
        return _POSTGRES_ERROR_MAP

    def _get_extra_exception_handlers(self) -> list[tuple[type[Exception], ExceptionHandler]]:
        return [(SSLRequiredError, lambda e: (False, str(e)))]

    def _get_foreign_keys(
        self, host: str, port: int, config: PostgresSourceConfig, names: list[str] | None
    ) -> ForeignKeyMapping:
        return get_postgres_foreign_keys(
            host=host,
            port=port,
            user=config.user,
            password=config.password,
            database=config.database,
            schema=config.schema,
            names=names,
        )

    def _get_row_counts(
        self, host: str, port: int, config: PostgresSourceConfig, names: list[str] | None
    ) -> RowCountMapping:
        return get_postgres_row_count(
            host=host,
            port=port,
            user=config.user,
            password=config.password,
            database=config.database,
            schema=config.schema,
            names=names,
        )

    def _get_extra_source_kwargs(self, config: PostgresSourceConfig, inputs: SourceInputs) -> dict[str, Any]:
        from products.data_warehouse.backend.models.external_data_schema import ExternalDataSchema

        schema = ExternalDataSchema.objects.select_related("source").get(id=inputs.schema_id)
        # Require SSL for sources created after the cutoff date
        require_ssl = schema.source.created_at >= SSL_REQUIRED_AFTER_DATE

        return {
            "sslmode": "prefer",
            "chunk_size_override": schema.chunk_size_override,
            "team_id": inputs.team_id,
            "require_ssl": require_ssl,
        }

    def get_connection_metadata(
        self, config: PostgresSourceConfig, team_id: int, require_ssl: bool = False
    ) -> dict[str, object]:
        with self.with_ssh_tunnel(config) as (host, port):
            return get_postgres_connection_metadata(
                host=host,
                port=port,
                user=config.user,
                password=config.password,
                database=config.database,
                require_ssl=require_ssl,
            )
