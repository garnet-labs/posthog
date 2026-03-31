"""CDC Temporal activities.

cdc_extract_activity: Core extraction — reads WAL, decodes, batches, writes to
S3 via pipeline, and sends Kafka notifications for streaming schemas. Defers
Kafka for snapshot schemas.

validate_cdc_prerequisites_activity: Wraps prerequisite validator for Temporal.
"""

from __future__ import annotations

import uuid
import typing
import datetime as dt
import dataclasses

from django.db import close_old_connections

import structlog
from temporalio import activity

from posthog.temporal.data_imports.cdc.batcher import ChangeEventBatcher
from posthog.temporal.data_imports.pipelines.pipeline_v3.kafka.common import SyncTypeLiteral
from posthog.temporal.data_imports.pipelines.pipeline_v3.kafka.producer import KafkaBatchProducer
from posthog.temporal.data_imports.pipelines.pipeline_v3.s3.writer import S3BatchWriter
from posthog.temporal.data_imports.sources.postgres.cdc.stream_reader import PgCDCConnectionParams, PgCDCStreamReader

from products.data_warehouse.backend.models import ExternalDataJob, ExternalDataSchema, ExternalDataSource

logger = structlog.get_logger(__name__)


@dataclasses.dataclass
class CDCExtractInput:
    team_id: int
    source_id: uuid.UUID

    @property
    def properties_to_log(self) -> dict[str, typing.Any]:
        return {
            "team_id": self.team_id,
            "source_id": str(self.source_id),
        }


@dataclasses.dataclass
class ValidateCDCPrerequisitesInput:
    team_id: int
    source_id: uuid.UUID
    management_mode: str
    tables: list[str]
    schema: str
    slot_name: str | None
    publication_name: str | None


def _get_pg_connection_params(source: ExternalDataSource) -> PgCDCConnectionParams:
    """Extract PgCDCConnectionParams from source job_inputs."""
    inputs = source.job_inputs or {}
    return PgCDCConnectionParams(
        host=inputs.get("host", ""),
        port=int(inputs.get("port", 5432)),
        database=inputs.get("database", ""),
        user=inputs.get("user", ""),
        password=inputs.get("password", ""),
        sslmode=inputs.get("sslmode", "prefer"),
        slot_name=inputs.get("cdc_slot_name", ""),
        publication_name=inputs.get("cdc_publication_name", ""),
    )


def _get_cdc_schemas(source: ExternalDataSource) -> list[ExternalDataSchema]:
    """Get all active CDC schemas for a source."""
    return list(
        ExternalDataSchema.objects.filter(
            source=source,
            sync_type=ExternalDataSchema.SyncType.CDC,
            should_sync=True,
        ).exclude(deleted=True)
    )


def _flush_deferred_runs(
    schema: ExternalDataSchema,
    source: ExternalDataSource,
    log: structlog.types.FilteringBoundLogger,
) -> None:
    """Send Kafka messages for deferred CDC runs from the snapshot phase.

    Called when a schema has just transitioned to cdc_mode="streaming" and has
    entries in sync_type_config["cdc_deferred_runs"].
    """
    deferred_runs: list[dict] = schema.sync_type_config.get("cdc_deferred_runs", [])
    if not deferred_runs:
        return

    log.info(
        "flushing_deferred_cdc_runs",
        schema_id=str(schema.id),
        deferred_count=len(deferred_runs),
    )

    for run_meta in deferred_runs:
        job_id = run_meta["job_id"]
        run_uuid = run_meta["run_uuid"]
        batch_results = run_meta.get("batch_results", [])
        total_batches = run_meta.get("total_batches", len(batch_results))
        total_rows = run_meta.get("total_rows", 0)

        producer = KafkaBatchProducer(
            team_id=schema.team_id,
            job_id=job_id,
            schema_id=str(schema.id),
            source_id=str(source.id),
            resource_name=schema.name,
            sync_type=typing.cast(SyncTypeLiteral, "cdc"),
            run_uuid=run_uuid,
            logger=log,
            primary_keys=run_meta.get("primary_keys"),
        )

        from posthog.temporal.data_imports.pipelines.pipeline_v3.s3 import BatchWriteResult

        for i, br in enumerate(batch_results):
            is_final = i == len(batch_results) - 1
            result = BatchWriteResult(
                s3_path=br["s3_path"],
                row_count=br["row_count"],
                byte_size=br["byte_size"],
                batch_index=br["batch_index"],
                timestamp_ns=br.get("timestamp_ns", 0),
            )
            producer.send_batch_notification(
                batch_result=result,
                is_final_batch=is_final,
                total_batches=total_batches if is_final else None,
                total_rows=total_rows if is_final else None,
                data_folder=run_meta.get("data_folder"),
                schema_path=run_meta.get("schema_path"),
            )

        producer.flush()

    schema.sync_type_config["cdc_deferred_runs"] = []
    schema.save(update_fields=["sync_type_config", "updated_at"])

    log.info("deferred_runs_flushed", schema_id=str(schema.id))


@activity.defn
def cdc_extract_activity(inputs: CDCExtractInput) -> None:
    """Core CDC extraction activity.

    1. Connect to source PG, read all pending WAL changes
    2. Decode and batch by table
    3. For each CDC schema:
       - Flush deferred runs if transitioning from snapshot → streaming
       - Write new events to S3
       - Send Kafka notification (streaming) or defer (snapshot)
    4. Advance slot position
    5. Update cdc_last_log_position per schema
    """
    close_old_connections()

    log = logger.bind(team_id=inputs.team_id, source_id=str(inputs.source_id))
    log.info("cdc_extract_started")

    source = ExternalDataSource.objects.get(pk=inputs.source_id)
    cdc_schemas = _get_cdc_schemas(source)

    if not cdc_schemas:
        log.info("no_cdc_schemas_found")
        return

    cdc_table_names = {s.name for s in cdc_schemas}
    schema_by_name: dict[str, ExternalDataSchema] = {s.name: s for s in cdc_schemas}

    params = _get_pg_connection_params(source)
    reader = PgCDCStreamReader(params)

    created_jobs: list[ExternalDataJob] = []

    # Mark CDC schemas as Running at the start
    for schema in cdc_schemas:
        schema.status = ExternalDataSchema.Status.RUNNING
        schema.save(update_fields=["status", "updated_at"])

    try:
        reader.connect()

        # Build PK map from schema metadata (stored at source creation)
        pk_columns_by_table: dict[str, list[str]] = {}
        for schema in cdc_schemas:
            stored_pks = schema.sync_type_config.get("primary_key_columns", [])
            if stored_pks:
                pk_columns_by_table[schema.name] = stored_pks

        # Fall back to information_schema for any tables missing PKs
        missing_pk_tables = [t for t in cdc_table_names if t not in pk_columns_by_table]
        if missing_pk_tables:
            db_schema = (source.job_inputs or {}).get("schema", "public")
            queried_pks = reader.get_primary_key_columns(db_schema, missing_pk_tables)
            pk_columns_by_table.update(queried_pks)
            # Persist discovered PKs to avoid re-querying
            for schema in cdc_schemas:
                if schema.name in queried_pks:
                    schema.sync_type_config["primary_key_columns"] = queried_pks[schema.name]
                    schema.save(update_fields=["sync_type_config", "updated_at"])

        log.info("pk_columns_loaded", tables=list(pk_columns_by_table.keys()))

        batcher = ChangeEventBatcher()
        last_end_lsn: str | None = None
        event_count = 0

        for event in reader.read_changes():
            activity.heartbeat()

            if event.table_name not in cdc_table_names:
                continue

            batcher.add(event)
            last_end_lsn = event.position_serialized
            event_count += 1

        log.info("wal_changes_read", event_count=event_count, tables=batcher.table_names)
        if event_count == 0:
            now = dt.datetime.now(tz=dt.UTC)
            for schema in cdc_schemas:
                schema.status = ExternalDataSchema.Status.COMPLETED
                schema.latest_error = None
                schema.last_synced_at = now
                schema.save(update_fields=["status", "latest_error", "last_synced_at", "updated_at"])
            log.info("no_wal_changes")
            return

        # Detect PK changes from decoder's Relation messages
        for table_name in batcher.table_names:
            decoder_pks = reader._decoder.get_key_columns(table_name)
            stored_pks = pk_columns_by_table.get(table_name, [])
            if decoder_pks and decoder_pks != stored_pks:
                log.warning("pk_columns_changed", table=table_name, old=stored_pks, new=decoder_pks)
                pk_columns_by_table[table_name] = decoder_pks
                schema = schema_by_name.get(table_name)
                if schema is not None:
                    schema.sync_type_config["primary_key_columns"] = decoder_pks
                    schema.save(update_fields=["sync_type_config", "updated_at"])

        # Check for truncated tables — mark for re-snapshot
        for table_name in reader.truncated_tables:
            schema = schema_by_name.get(table_name)
            if schema is not None:
                log.warning("truncate_detected", table=table_name, schema_id=str(schema.id))
                schema.sync_type_config["cdc_mode"] = "snapshot"
                schema.sync_type_config.pop("cdc_last_log_position", None)
                schema.initial_sync_complete = False
                schema.save(update_fields=["sync_type_config", "initial_sync_complete", "updated_at"])
                # Unpause the per-schema ExternalDataJobWorkflow schedule so
                # the initial snapshot can run again
                try:
                    from products.data_warehouse.backend.data_load.service import unpause_external_data_schedule

                    unpause_external_data_schedule(str(schema.id))
                    log.info("unpaused_schema_schedule_for_resnapshot", schema_id=str(schema.id))
                except Exception:
                    log.warning("failed_to_unpause_schema_schedule", schema_id=str(schema.id))
        reader.clear_truncated_tables()

        # Flush deferred runs for schemas that just transitioned to streaming
        for schema in cdc_schemas:
            if schema.cdc_mode == "streaming" and schema.sync_type_config.get("cdc_deferred_runs"):
                _flush_deferred_runs(schema, source, log)

        # Process new events
        tables = batcher.flush()

        for table_name, pa_table in tables.items():
            schema = schema_by_name.get(table_name)
            if schema is None:
                continue

            activity.heartbeat()

            job = ExternalDataJob.objects.create(
                team_id=inputs.team_id,
                pipeline=source,
                schema=schema,
                status=ExternalDataJob.Status.RUNNING,
                rows_synced=0,
                workflow_id=activity.info().workflow_id,
                workflow_run_id=activity.info().workflow_run_id,
                pipeline_version=ExternalDataJob.PipelineVersion.V2,
            )
            created_jobs.append(job)

            run_uuid = str(uuid.uuid4())
            s3_writer = S3BatchWriter(
                logger=log,
                job=job,
                schema_id=str(schema.id),
                run_uuid=run_uuid,
            )

            batch_result = s3_writer.write_batch(pa_table, batch_index=0)
            schema_path = s3_writer.write_schema()

            log.info(
                "cdc_batch_written",
                table=table_name,
                rows=pa_table.num_rows,
                s3_path=batch_result.s3_path,
                cdc_mode=schema.cdc_mode,
            )

            key_columns = pk_columns_by_table.get(table_name, [])

            if schema.cdc_mode == "streaming":
                producer = KafkaBatchProducer(
                    team_id=inputs.team_id,
                    job_id=str(job.id),
                    schema_id=str(schema.id),
                    source_id=str(source.id),
                    resource_name=schema.name,
                    sync_type=typing.cast(SyncTypeLiteral, "cdc"),
                    run_uuid=run_uuid,
                    logger=log,
                    primary_keys=key_columns or None,
                )
                producer.send_batch_notification(
                    batch_result=batch_result,
                    is_final_batch=True,
                    total_batches=1,
                    total_rows=pa_table.num_rows,
                    data_folder=s3_writer.get_data_folder(),
                    schema_path=schema_path,
                )
                producer.flush()

                # Don't mark job as COMPLETED here — the Kafka consumer will
                # mark it after successfully loading data into DeltaLake.
                job.rows_synced = pa_table.num_rows
                job.save(update_fields=["rows_synced", "updated_at"])

            elif schema.cdc_mode == "snapshot":
                # Defer Kafka notification — store run metadata
                deferred = schema.sync_type_config.setdefault("cdc_deferred_runs", [])
                deferred.append(
                    {
                        "job_id": str(job.id),
                        "run_uuid": run_uuid,
                        "data_folder": s3_writer.get_data_folder(),
                        "schema_path": schema_path,
                        "total_batches": 1,
                        "total_rows": pa_table.num_rows,
                        "primary_keys": key_columns or None,
                        "batch_results": [
                            {
                                "s3_path": batch_result.s3_path,
                                "row_count": batch_result.row_count,
                                "byte_size": batch_result.byte_size,
                                "batch_index": batch_result.batch_index,
                                "timestamp_ns": batch_result.timestamp_ns,
                            }
                        ],
                    }
                )
                schema.save(update_fields=["sync_type_config", "updated_at"])
                log.info("cdc_batch_deferred", table=table_name, run_uuid=run_uuid)

                # For snapshot mode, the Kafka message is deferred so the consumer
                # won't process it yet. Mark the job as completed here since there's
                # nothing else to do until the schema transitions to streaming.
                job.rows_synced = pa_table.num_rows
                job.status = ExternalDataJob.Status.COMPLETED
                job.finished_at = dt.datetime.now(tz=dt.UTC)
                job.save(update_fields=["rows_synced", "status", "finished_at", "updated_at"])

        # Advance slot after successful S3 writes
        if last_end_lsn is not None:
            reader.confirm_position(last_end_lsn)
            log.info("slot_advanced", position=last_end_lsn)

            # Update per-schema cdc_last_log_position (skip schemas reset to snapshot mode)
            for schema in cdc_schemas:
                if schema.sync_type_config.get("cdc_mode") == "snapshot":
                    continue
                schema.sync_type_config["cdc_last_log_position"] = last_end_lsn
                schema.save(update_fields=["sync_type_config", "updated_at"])

    except Exception as exc:
        log.exception("cdc_extract_failed")
        for job in created_jobs:
            if job.status == ExternalDataJob.Status.RUNNING:
                job.status = ExternalDataJob.Status.FAILED
                job.latest_error = str(exc)[:1000]
                job.finished_at = dt.datetime.now(tz=dt.UTC)
                job.save(update_fields=["status", "latest_error", "finished_at", "updated_at"])
        for schema in cdc_schemas:
            schema.status = ExternalDataSchema.Status.FAILED
            schema.latest_error = str(exc)[:1000]
            schema.save(update_fields=["status", "latest_error", "updated_at"])
        raise
    finally:
        reader.close()

    now = dt.datetime.now(tz=dt.UTC)
    for schema in cdc_schemas:
        schema.status = ExternalDataSchema.Status.COMPLETED
        schema.latest_error = None
        schema.last_synced_at = now
        schema.save(update_fields=["status", "latest_error", "last_synced_at", "updated_at"])

    log.info("cdc_extract_completed", event_count=event_count)


@activity.defn
def validate_cdc_prerequisites_activity(inputs: ValidateCDCPrerequisitesInput) -> list[str]:
    """Validate CDC prerequisites for a source. Returns list of error messages."""
    import psycopg

    from posthog.temporal.data_imports.sources.postgres.cdc.prerequisite_validator import validate_cdc_prerequisites

    close_old_connections()

    source = ExternalDataSource.objects.get(pk=inputs.source_id)
    job_inputs = source.job_inputs or {}

    conn = psycopg.connect(
        host=job_inputs.get("host", ""),
        port=int(job_inputs.get("port", 5432)),
        dbname=job_inputs.get("database", ""),
        user=job_inputs.get("user", ""),
        password=job_inputs.get("password", ""),
        connect_timeout=15,
    )

    try:
        return validate_cdc_prerequisites(
            conn=conn,
            management_mode=inputs.management_mode,  # type: ignore[arg-type]
            tables=inputs.tables,
            schema=inputs.schema,
            slot_name=inputs.slot_name,
            publication_name=inputs.publication_name,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Orphan slot sweeper
# ---------------------------------------------------------------------------

DEFAULT_LAG_WARNING_THRESHOLD_MB = 1024
DEFAULT_LAG_CRITICAL_THRESHOLD_MB = 10240


@activity.defn
def cleanup_orphan_slots_activity() -> None:
    """Safety-net sweeper: clean up orphaned CDC slots and monitor WAL lag.

    1. For deleted/inactive PostHog-managed sources → drop slot + publication
    2. For active sources → check WAL lag:
       - Warning threshold: log warning, update source status
       - Critical threshold (PostHog-managed, safety net on): drop slot, mark error
       - Self-managed: never drop, only warn
    """
    import psycopg

    from posthog.temporal.data_imports.sources.postgres.cdc.slot_manager import (
        drop_slot_and_publication,
        get_slot_lag_bytes,
    )

    close_old_connections()

    log = logger.bind()
    log.info("cleanup_orphan_slots_started")

    # Find all sources with CDC enabled
    cdc_sources = list(
        ExternalDataSource.objects.filter(
            job_inputs__contains={"cdc_enabled": True},
        )
    )

    for source in cdc_sources:
        job_inputs = source.job_inputs or {}
        slot_name = job_inputs.get("cdc_slot_name")
        pub_name = job_inputs.get("cdc_publication_name")
        management_mode = job_inputs.get("cdc_management_mode", "posthog")

        if not slot_name or not pub_name:
            continue

        source_log = log.bind(
            source_id=str(source.id),
            team_id=source.team_id,
            slot_name=slot_name,
            management_mode=management_mode,
        )

        # 1. Deleted sources — clean up PostHog-managed slots
        if source.deleted and management_mode == "posthog":
            source_log.info("cleaning_up_deleted_source_slot")
            try:
                conn = psycopg.connect(
                    host=job_inputs.get("host", ""),
                    port=int(job_inputs.get("port", 5432)),
                    dbname=job_inputs.get("database", ""),
                    user=job_inputs.get("user", ""),
                    password=job_inputs.get("password", ""),
                    connect_timeout=10,
                )
                try:
                    drop_slot_and_publication(conn, slot_name, pub_name)
                finally:
                    conn.close()
            except Exception:
                source_log.exception("failed_to_cleanup_deleted_source_slot")
            continue

        # 2. Active sources — check WAL lag
        if source.deleted:
            continue

        try:
            conn = psycopg.connect(
                host=job_inputs.get("host", ""),
                port=int(job_inputs.get("port", 5432)),
                dbname=job_inputs.get("database", ""),
                user=job_inputs.get("user", ""),
                password=job_inputs.get("password", ""),
                connect_timeout=10,
            )
            try:
                lag_bytes = get_slot_lag_bytes(conn, slot_name)
            finally:
                conn.close()
        except Exception:
            source_log.exception("failed_to_check_slot_lag")
            continue

        if lag_bytes is None:
            source_log.warning("slot_not_found_or_no_flush_lsn")
            continue

        lag_mb = lag_bytes / (1024 * 1024)
        warning_threshold = job_inputs.get("cdc_lag_warning_threshold_mb", DEFAULT_LAG_WARNING_THRESHOLD_MB)
        critical_threshold = job_inputs.get("cdc_lag_critical_threshold_mb", DEFAULT_LAG_CRITICAL_THRESHOLD_MB)
        auto_drop = job_inputs.get("cdc_auto_drop_slot", True)

        if lag_mb >= critical_threshold:
            source_log.error(
                "slot_lag_critical",
                lag_mb=round(lag_mb, 1),
                threshold_mb=critical_threshold,
            )

            if management_mode == "posthog" and auto_drop:
                source_log.warning("auto_dropping_slot_critical_lag")
                try:
                    conn = psycopg.connect(
                        host=job_inputs.get("host", ""),
                        port=int(job_inputs.get("port", 5432)),
                        dbname=job_inputs.get("database", ""),
                        user=job_inputs.get("user", ""),
                        password=job_inputs.get("password", ""),
                        connect_timeout=10,
                    )
                    try:
                        drop_slot_and_publication(conn, slot_name, pub_name)
                    finally:
                        conn.close()

                    source.status = ExternalDataSource.Status.ERROR
                    source.save(update_fields=["status", "updated_at"])
                except Exception:
                    source_log.exception("failed_to_auto_drop_slot")
            elif management_mode == "self_managed":
                source.status = ExternalDataSource.Status.ERROR
                source.save(update_fields=["status", "updated_at"])

        elif lag_mb >= warning_threshold:
            source_log.warning(
                "slot_lag_warning",
                lag_mb=round(lag_mb, 1),
                threshold_mb=warning_threshold,
            )

    log.info("cleanup_orphan_slots_completed", sources_checked=len(cdc_sources))
