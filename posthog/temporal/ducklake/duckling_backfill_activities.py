from __future__ import annotations

import duckdb
from structlog.contextvars import bind_contextvars
from temporalio import activity

from posthog.temporal.common.heartbeat_sync import HeartbeaterSync
from posthog.temporal.common.logger import get_logger
from posthog.temporal.ducklake.duckling_backfill_inputs import (
    DucklingCheckAutoPauseInputs,
    DucklingCopyFilesInputs,
    DucklingCopyFilesResult,
    DucklingRegisterInputs,
    DucklingResolveConfigInputs,
    DucklingResolveConfigResult,
    DucklingUpdateStatusInputs,
)

LOGGER = get_logger(__name__)

# DuckDB memory limit — leave headroom for the Temporal worker process
DUCKDB_MEMORY_LIMIT = "4GB"

# Auto-pause: if >= FAILURE_THRESHOLD of the last FAILURE_CHECK_WINDOW runs failed,
# skip the team until manual intervention (matching batch exports pattern)
FAILURE_THRESHOLD = 5
FAILURE_CHECK_WINDOW = 10


@activity.defn
async def check_auto_pause_activity(inputs: DucklingCheckAutoPauseInputs) -> bool:
    """Check if a team should be skipped due to too many recent failures.

    Checks the last FAILURE_CHECK_WINDOW runs for the team. If >= FAILURE_THRESHOLD
    are failed, returns True (auto-paused).
    """
    bind_contextvars(team_id=inputs.team_id, data_type=inputs.data_type)

    from posthog.ducklake.models import DucklingBackfillRun
    from posthog.sync import database_sync_to_async

    failed_count = await database_sync_to_async(
        lambda: (
            DucklingBackfillRun.objects.filter(
                id__in=DucklingBackfillRun.objects.filter(
                    team_id=inputs.team_id,
                    data_type=inputs.data_type,
                )
                .order_by("-updated_at")
                .values("id")[:FAILURE_CHECK_WINDOW]
            )
            .filter(status="failed")
            .count()
        )
    )()
    return failed_count >= FAILURE_THRESHOLD


@activity.defn
async def resolve_duckling_config_activity(inputs: DucklingResolveConfigInputs) -> DucklingResolveConfigResult:
    """Load DuckLakeCatalog and assume cross-account IAM role for S3 access."""
    bind_contextvars(team_id=inputs.team_id, data_type=inputs.data_type)
    logger = LOGGER.bind()

    from posthog.ducklake.models import DuckLakeCatalog
    from posthog.ducklake.storage import _get_cross_account_credentials
    from posthog.sync import database_sync_to_async

    catalog = await database_sync_to_async(
        lambda: DuckLakeCatalog.objects.select_related("team").get(team_id=inputs.team_id)
    )()

    logger.info(
        "Resolving duckling config",
        bucket=catalog.bucket,
        region=catalog.bucket_region,
    )

    access_key, secret_key, session_token = await database_sync_to_async(
        lambda: _get_cross_account_credentials(
            catalog.cross_account_role_arn,
            external_id=catalog.cross_account_external_id,
        )
    )()

    return DucklingResolveConfigResult(
        bucket=catalog.bucket,
        region=catalog.bucket_region,
        role_arn=catalog.cross_account_role_arn,
        external_id=catalog.cross_account_external_id,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
    )


@activity.defn
def copy_partition_files_activity(inputs: DucklingCopyFilesInputs) -> DucklingCopyFilesResult:
    """Copy partition files from the shared DuckLake (megaduck) to a customer's S3 bucket.

    Queries the shared DuckLake catalog metadata to find S3 files for the given
    team+date partition, then uses boto3 copy_object to copy them directly to the
    customer's bucket, preserving the original relative path.
    """
    bind_contextvars(team_id=inputs.team_id, data_type=inputs.data_type, partition_key=inputs.partition_key)
    logger = LOGGER.bind()

    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import urlparse

    import boto3

    from posthog.ducklake.common import attach_catalog, get_config
    from posthog.ducklake.storage import DuckLakeStorageConfig, configure_connection

    date_parts = inputs.partition_key.split("-")
    if len(date_parts) != 3:
        raise ValueError(f"Invalid partition_key format, expected YYYY-MM-DD: {inputs.partition_key}")
    year, month, day = date_parts

    heartbeater = HeartbeaterSync(details=("duckling_copy_files", inputs.data_type), logger=logger)
    with heartbeater:
        conn = duckdb.connect(config={"memory_limit": DUCKDB_MEMORY_LIMIT})
        try:
            # Set up credentials for reading from the shared DuckLake bucket
            storage_config = DuckLakeStorageConfig.from_runtime()
            configure_connection(conn, storage_config)

            # Attach the shared DuckLake catalog (megaduck) for metadata queries
            shared_config = get_config()
            attach_catalog(conn, shared_config, alias="megaduck")

            # Find the table_id for the data_type table in the megaduck catalog
            table_name = inputs.data_type  # "events" or "persons"
            table_row = conn.execute(
                """
                SELECT t.table_id, t.data_path
                FROM __ducklake_metadata_megaduck.ducklake_table t
                JOIN __ducklake_metadata_megaduck.ducklake_schema s
                    ON t.schema_id = s.schema_id
                WHERE s.schema_name = 'posthog'
                  AND t.table_name = ?
                """,
                [table_name],
            ).fetchone()

            if table_row is None:
                raise ValueError(f"Table posthog.{table_name} not found in megaduck catalog")

            table_id, table_data_path = table_row

            # Query catalog metadata for files matching this partition
            files = conn.execute(
                """
                SELECT df.data_file_id, df.path, df.path_is_relative,
                       df.record_count, df.file_size_bytes
                FROM __ducklake_metadata_megaduck.ducklake_data_file df
                JOIN __ducklake_metadata_megaduck.ducklake_file_partition_value fp0
                    ON df.data_file_id = fp0.data_file_id AND fp0.partition_key_index = 0
                JOIN __ducklake_metadata_megaduck.ducklake_file_partition_value fp1
                    ON df.data_file_id = fp1.data_file_id AND fp1.partition_key_index = 1
                JOIN __ducklake_metadata_megaduck.ducklake_file_partition_value fp2
                    ON df.data_file_id = fp2.data_file_id AND fp2.partition_key_index = 2
                JOIN __ducklake_metadata_megaduck.ducklake_file_partition_value fp3
                    ON df.data_file_id = fp3.data_file_id AND fp3.partition_key_index = 3
                WHERE df.table_id = ?
                  AND df.end_snapshot IS NULL
                  AND fp0.partition_value = ?
                  AND fp1.partition_value = ?
                  AND fp2.partition_value = ?
                  AND fp3.partition_value = ?
                """,
                [table_id, str(inputs.team_id), year, month, day],
            ).fetchall()

        finally:
            conn.close()

        if not files:
            logger.info("No files found for partition")
            return DucklingCopyFilesResult(dest_s3_paths=[], total_records=0, total_bytes=0)

        # Resolve full S3 paths for source files
        source_bucket = shared_config["DUCKLAKE_BUCKET"]
        source_files: list[tuple[str, str, int, int]] = []  # (source_key, dest_key, records, bytes)

        for _file_id, path, path_is_relative, record_count, file_size_bytes in files:
            if path_is_relative:
                # Prepend the table's data_path to get the full S3 path
                if table_data_path:
                    full_path = f"{table_data_path.rstrip('/')}/{path}"
                else:
                    full_path = f"s3://{source_bucket}/{path}"
            else:
                full_path = path

            # Parse to extract bucket and key
            parsed = urlparse(full_path)
            source_key = parsed.path.lstrip("/")

            # Destination key is the same relative path in the customer bucket
            dest_key = source_key

            source_files.append((source_key, dest_key, record_count or 0, file_size_bytes or 0))

        logger.info(
            "Copying partition files",
            file_count=len(source_files),
            source_bucket=source_bucket,
            dest_bucket=inputs.dest_bucket,
        )

        # Create boto3 client with customer credentials for writing to destination
        dest_s3 = boto3.client(
            "s3",
            aws_access_key_id=inputs.aws_access_key_id,
            aws_secret_access_key=inputs.aws_secret_access_key,
            aws_session_token=inputs.aws_session_token,
            region_name=inputs.dest_region,
        )

        dest_s3_paths: list[str] = []
        total_records = 0
        total_bytes = 0

        def copy_one(file_info: tuple[str, str, int, int]) -> str:
            source_key, dest_key, _, _ = file_info
            dest_s3.copy_object(
                Bucket=inputs.dest_bucket,
                Key=dest_key,
                CopySource={"Bucket": source_bucket, "Key": source_key},
            )
            return f"s3://{inputs.dest_bucket}/{dest_key}"

        with ThreadPoolExecutor(max_workers=10) as executor:
            dest_s3_paths = list(executor.map(copy_one, source_files))

        for _, _, records, size_bytes in source_files:
            total_records += records
            total_bytes += size_bytes

        logger.info(
            "Copy complete",
            files_copied=len(dest_s3_paths),
            total_records=total_records,
            total_bytes=total_bytes,
        )
        return DucklingCopyFilesResult(
            dest_s3_paths=dest_s3_paths,
            total_records=total_records,
            total_bytes=total_bytes,
        )


@activity.defn
def register_with_ducklake_activity(inputs: DucklingRegisterInputs) -> None:
    """Register Parquet files with the customer's DuckLake catalog via duckgres."""
    bind_contextvars(team_id=inputs.team_id, data_type=inputs.data_type)
    logger = LOGGER.bind()

    from posthog.ducklake.common import attach_catalog, get_duckgres_server_for_team, get_team_config, is_dev_mode
    from posthog.ducklake.storage import configure_cross_account_connection, connect_to_duckgres, setup_duckgres_session

    heartbeater = HeartbeaterSync(details=("duckling_backfill", inputs.data_type), logger=logger)
    with heartbeater:
        if is_dev_mode():
            # Dev mode fallback: use DuckDB directly
            from posthog.ducklake.models import DuckLakeCatalog

            catalog = DuckLakeCatalog.objects.get(team_id=inputs.team_id)
            destination = catalog.to_cross_account_destination()
            catalog_config = get_team_config(catalog.team_id)
            alias = "ducklake"

            conn = duckdb.connect(config={"memory_limit": DUCKDB_MEMORY_LIMIT})
            try:
                configure_cross_account_connection(conn, destinations=[destination])
                attach_catalog(conn, catalog_config, alias=alias)

                for s3_path in inputs.s3_paths:
                    logger.info("Registering file with DuckLake (dev)", s3_path=s3_path)
                    conn.execute(
                        f"CALL ducklake_add_data_files('{alias}', ?, ?, schema => 'posthog')",
                        [inputs.data_type, s3_path],
                    )
            finally:
                conn.close()
        else:
            # Production: register via duckgres
            server = get_duckgres_server_for_team(inputs.team_id)
            if server is None:
                raise ValueError(f"No DuckgresServer configured for team {inputs.team_id}")

            with connect_to_duckgres(server) as pg_conn:
                setup_duckgres_session(pg_conn)

                for s3_path in inputs.s3_paths:
                    logger.info("Registering file with DuckLake via duckgres", s3_path=s3_path)
                    pg_conn.execute(
                        "CALL ducklake_add_data_files('ducklake', %s, %s, schema => 'posthog')",
                        [inputs.data_type, s3_path],
                    )

    logger.info("All files registered with DuckLake", count=len(inputs.s3_paths))


@activity.defn
async def update_backfill_run_status_activity(inputs: DucklingUpdateStatusInputs) -> None:
    """Create or update the DucklingBackfillRun status."""
    bind_contextvars(team_id=inputs.team_id, data_type=inputs.data_type, partition_key=inputs.partition_key)
    logger = LOGGER.bind()

    from posthog.ducklake.models import DucklingBackfillRun
    from posthog.sync import database_sync_to_async

    await database_sync_to_async(
        lambda: DucklingBackfillRun.objects.update_or_create(
            team_id=inputs.team_id,
            data_type=inputs.data_type,
            partition_key=inputs.partition_key,
            defaults={
                "status": inputs.status,
                "workflow_id": inputs.workflow_id,
                "error_message": inputs.error_message,
                "records_exported": inputs.records_exported,
                "bytes_exported": inputs.bytes_exported,
            },
        )
    )()

    logger.info("Updated backfill run status", status=inputs.status)
