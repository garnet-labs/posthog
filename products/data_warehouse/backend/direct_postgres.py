from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Q

from posthog.temporal.data_imports.sources.common.schema import SourceSchema

from products.data_warehouse.backend.models.external_data_source import ExternalDataSource
from products.data_warehouse.backend.models.util import postgres_column_to_dwh_column, postgres_columns_to_dwh_columns

if TYPE_CHECKING:
    from products.data_warehouse.backend.models.table import DataWarehouseTable

DIRECT_POSTGRES_URL_PATTERN = "direct://postgres"
DIRECT_POSTGRES_SCHEMA_OPTION = "direct_postgres_schema"
DIRECT_POSTGRES_TABLE_OPTION = "direct_postgres_table"

type DirectPostgresColumns = dict[str, dict[str, Any]]


def _normalize_default_schema(default_schema: str | None) -> str | None:
    if not isinstance(default_schema, str):
        return None

    normalized_default_schema = default_schema.strip()
    return normalized_default_schema or None


def postgres_schema_metadata_to_dwh_columns(schema_metadata: dict[str, Any] | None) -> DirectPostgresColumns:
    resolved_columns: DirectPostgresColumns = {}
    if not schema_metadata:
        return resolved_columns

    columns = schema_metadata.get("columns")
    if not isinstance(columns, list):
        return resolved_columns

    for column in columns:
        if not isinstance(column, dict):
            continue

        column_name = column.get("name")
        postgres_type = column.get("data_type")
        nullable = bool(column.get("is_nullable"))

        if not isinstance(column_name, str) or not isinstance(postgres_type, str):
            continue

        resolved_columns[column_name] = postgres_column_to_dwh_column(column_name, postgres_type, nullable)

    return resolved_columns


def postgres_schema_metadata(
    columns: list[tuple[str, str, bool]],
    foreign_keys: list[tuple[str, str, str]] | None = None,
    source_schema: str | None = None,
    source_table_name: str | None = None,
) -> dict[str, Any]:
    return {
        "columns": [
            {"name": column_name, "data_type": postgres_type, "is_nullable": nullable}
            for column_name, postgres_type, nullable in columns
        ],
        "foreign_keys": [
            {"column": column_name, "target_table": target_table, "target_column": target_column}
            for column_name, target_table, target_column in (foreign_keys or [])
        ],
        "source_schema": source_schema,
        "source_table_name": source_table_name,
    }


def get_direct_postgres_location(
    *,
    schema_name: str,
    schema_metadata: dict[str, Any] | None = None,
    default_schema: str | None = None,
) -> tuple[str, str]:
    source_schema = schema_metadata.get("source_schema") if isinstance(schema_metadata, dict) else None
    source_table_name = schema_metadata.get("source_table_name") if isinstance(schema_metadata, dict) else None
    normalized_default_schema = _normalize_default_schema(default_schema)

    if isinstance(source_schema, str) and isinstance(source_table_name, str):
        return source_schema, source_table_name

    if normalized_default_schema is None and "." in schema_name:
        inferred_schema, inferred_table_name = schema_name.split(".", 1)
        return inferred_schema, inferred_table_name

    return normalized_default_schema or "public", schema_name


def get_direct_postgres_table_options(*, source_schema: str, source_table_name: str) -> dict[str, str]:
    return {
        DIRECT_POSTGRES_SCHEMA_OPTION: source_schema,
        DIRECT_POSTGRES_TABLE_OPTION: source_table_name,
    }


def upsert_direct_postgres_table(
    existing_table: DataWarehouseTable | None,
    *,
    schema_name: str,
    source: ExternalDataSource,
    columns: DirectPostgresColumns,
    source_schema: str,
    source_table_name: str,
) -> DataWarehouseTable:
    from products.data_warehouse.backend.models.table import DataWarehouseTable

    options = {
        **(existing_table.options if existing_table is not None and isinstance(existing_table.options, dict) else {}),
        **get_direct_postgres_table_options(source_schema=source_schema, source_table_name=source_table_name),
    }

    if existing_table is None:
        return DataWarehouseTable.objects.create(
            name=schema_name,
            format=DataWarehouseTable.TableFormat.Parquet,
            team_id=source.team_id,
            url_pattern=DIRECT_POSTGRES_URL_PATTERN,
            external_data_source=source,
            columns=columns,
            options=options,
        )

    existing_table.name = schema_name
    existing_table.url_pattern = DIRECT_POSTGRES_URL_PATTERN
    existing_table.external_data_source = source
    existing_table.columns = columns
    existing_table.options = options
    existing_table.deleted = False
    existing_table.deleted_at = None
    existing_table.save(
        update_fields=[
            "name",
            "url_pattern",
            "external_data_source",
            "columns",
            "options",
            "deleted",
            "deleted_at",
            "updated_at",
        ]
    )
    return existing_table


def hide_direct_postgres_table(table: DataWarehouseTable | None) -> None:
    if table is not None and not table.deleted:
        table.soft_delete()


def reconcile_direct_postgres_schemas(
    *,
    source: ExternalDataSource,
    source_schemas: list[SourceSchema],
    team_id: int,
) -> list[str]:
    from products.data_warehouse.backend.models.external_data_schema import ExternalDataSchema

    source_schema_names = [schema.name for schema in source_schemas]
    schema_models = {
        schema.name: schema
        for schema in ExternalDataSchema.objects.filter(team_id=team_id, source_id=source.id, deleted=False)
    }

    for source_schema in source_schemas:
        schema_model = schema_models.get(source_schema.name)
        if schema_model is None:
            continue

        resolved_source_schema, resolved_source_table_name = get_direct_postgres_location(
            schema_name=source_schema.name,
            schema_metadata={
                "source_schema": source_schema.source_schema,
                "source_table_name": source_schema.source_table_name,
            },
            default_schema=(source.job_inputs or {}).get("schema"),
        )
        schema_metadata = postgres_schema_metadata(
            source_schema.columns,
            source_schema.foreign_keys,
            source_schema=resolved_source_schema,
            source_table_name=resolved_source_table_name,
        )
        schema_model.sync_type_config = {**(schema_model.sync_type_config or {}), "schema_metadata": schema_metadata}
        schema_model.save(update_fields=["sync_type_config", "updated_at"])

        if not schema_model.should_sync:
            hide_direct_postgres_table(schema_model.table)
            continue

        table_model = upsert_direct_postgres_table(
            schema_model.table,
            schema_name=source_schema.name,
            source=source,
            columns=postgres_columns_to_dwh_columns(source_schema.columns),
            source_schema=resolved_source_schema,
            source_table_name=resolved_source_table_name,
        )
        if schema_model.table_id != table_model.id:
            schema_model.table = table_model
            schema_model.save(update_fields=["table"])

    stale_schema_names: list[str] = []
    stale_schemas = ExternalDataSchema.objects.filter(
        Q(team_id=team_id, source_id=source.id),
        Q(deleted=False) | Q(table__deleted=False),
    ).exclude(name__in=source_schema_names)

    for stale_schema in stale_schemas:
        hide_direct_postgres_table(stale_schema.table)
        if not stale_schema.deleted:
            stale_schema.soft_delete()
        stale_schema_names.append(stale_schema.name)

    return stale_schema_names
