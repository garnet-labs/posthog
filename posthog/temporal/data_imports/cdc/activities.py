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

import pyarrow as pa
import structlog
from temporalio import activity

from posthog.temporal.data_imports.cdc.adapters import get_cdc_adapter
from posthog.temporal.data_imports.cdc.batcher import (
    ChangeEventBatcher,
    build_scd2_table,
    deduplicate_table,
    enrich_delete_rows,
)
from posthog.temporal.data_imports.pipelines.pipeline_v3.kafka.common import SyncTypeLiteral
from posthog.temporal.data_imports.pipelines.pipeline_v3.kafka.producer import KafkaBatchProducer
from posthog.temporal.data_imports.pipelines.pipeline_v3.s3.writer import S3BatchWriter

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
            cdc_write_mode=run_meta.get("cdc_write_mode", "incremental_merge"),
            cdc_table_mode=run_meta.get("cdc_table_mode"),
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

    adapter = get_cdc_adapter(source)
    reader = adapter.create_reader(source)

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

        # ------------------------------------------------------------------
        # Per-resource tracker: reused across micro-batch flushes so that
        # each (table × write_mode) produces ONE job with sequential
        # S3 batch files, matching the multi-batch pattern of pipeline V3.
        # ------------------------------------------------------------------
        @dataclasses.dataclass
        class _WriteTracker:
            table_name: str
            write_resource_name: str
            cdc_write_mode: str
            cdc_table_mode: str
            key_columns: list[str]
            job: ExternalDataJob
            s3_writer: S3BatchWriter
            run_uuid: str
            batch_results: list  # list[BatchWriteResult]
            batch_index: int = 0
            total_rows: int = 0

        write_trackers: dict[str, _WriteTracker] = {}

        def _get_or_create_tracker(
            table_name: str,
            write_resource_name: str,
            cdc_write_mode: str,
            cdc_table_mode: str,
            key_columns: list[str],
            schema: ExternalDataSchema,
        ) -> _WriteTracker:
            tracker = write_trackers.get(write_resource_name)
            if tracker is not None:
                return tracker

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

            tracker = _WriteTracker(
                table_name=table_name,
                write_resource_name=write_resource_name,
                cdc_write_mode=cdc_write_mode,
                cdc_table_mode=cdc_table_mode,
                key_columns=key_columns,
                job=job,
                s3_writer=s3_writer,
                run_uuid=run_uuid,
                batch_results=[],
            )
            write_trackers[write_resource_name] = tracker
            return tracker

        def _send_kafka_batch(tracker: _WriteTracker, batch_result: typing.Any, is_final_batch: bool) -> None:
            """Send a single Kafka notification for a streaming tracker."""
            schema = schema_by_name[tracker.table_name]
            producer = KafkaBatchProducer(
                team_id=inputs.team_id,
                job_id=str(tracker.job.id),
                schema_id=str(schema.id),
                source_id=str(source.id),
                resource_name=tracker.write_resource_name,
                sync_type=typing.cast(SyncTypeLiteral, "cdc"),
                run_uuid=tracker.run_uuid,
                logger=log,
                primary_keys=tracker.key_columns or None,
                cdc_write_mode=tracker.cdc_write_mode,
                cdc_table_mode=tracker.cdc_table_mode,
            )
            producer.send_batch_notification(
                batch_result=batch_result,
                is_final_batch=is_final_batch,
                total_batches=tracker.batch_index if is_final_batch else None,
                total_rows=tracker.total_rows if is_final_batch else None,
                data_folder=tracker.s3_writer.get_data_folder() if is_final_batch else None,
                schema_path=tracker.s3_writer.write_schema() if is_final_batch else None,
            )
            producer.flush()

        def _store_deferred_batch(tracker: _WriteTracker, batch_result: typing.Any, schema: ExternalDataSchema) -> None:
            """Persist a batch result into the tracker's deferred entry in sync_type_config.

            Creates the entry on first call (keyed by run_uuid), appends to it on
            subsequent calls.  Saves immediately so progress survives process failures.

            IMPORTANT: This mutates the in-memory schema.sync_type_config and saves
            with update_fields=["sync_type_config"]. This is safe because
            cdc_extract_activity is single-threaded and all sync_type_config writes
            happen sequentially within this activity. Do not call from async contexts.
            """
            deferred = schema.sync_type_config.setdefault("cdc_deferred_runs", [])

            # Find existing entry for this run
            entry: dict | None = None
            for d in deferred:
                if d.get("run_uuid") == tracker.run_uuid:
                    entry = d
                    break

            if entry is None:
                entry = {
                    "job_id": str(tracker.job.id),
                    "run_uuid": tracker.run_uuid,
                    "data_folder": tracker.s3_writer.get_data_folder(),
                    "schema_path": None,  # written on finalization
                    "total_batches": 0,
                    "total_rows": 0,
                    "primary_keys": tracker.key_columns or None,
                    "cdc_write_mode": tracker.cdc_write_mode,
                    "cdc_table_mode": tracker.cdc_table_mode,
                    "batch_results": [],
                }
                deferred.append(entry)

            entry["batch_results"].append(
                {
                    "s3_path": batch_result.s3_path,
                    "row_count": batch_result.row_count,
                    "byte_size": batch_result.byte_size,
                    "batch_index": batch_result.batch_index,
                    "timestamp_ns": batch_result.timestamp_ns,
                }
            )
            entry["total_batches"] = tracker.batch_index
            entry["total_rows"] = tracker.total_rows

            schema.save(update_fields=["sync_type_config", "updated_at"])

        def _process_flush(tables: dict[str, pa.Table], is_final: bool = False) -> set[str]:
            """Enrich, transform, write to S3, and dispatch one micro-batch.

            Streaming schemas: Kafka sent immediately after each S3 write.
            Snapshot schemas: batch result persisted to sync_type_config immediately.

            Returns the set of write_resource_names that received data.
            """
            flushed: set[str] = set()

            for table_name, raw_table in tables.items():
                schema = schema_by_name.get(table_name)
                if schema is None:
                    continue

                activity.heartbeat()

                key_columns = pk_columns_by_table.get(table_name, [])
                cdc_table_mode = schema.cdc_table_mode

                enriched_table = enrich_delete_rows(raw_table, key_columns)

                batch_writes: list[tuple[pa.Table, str, str]] = []
                if cdc_table_mode == "consolidated":
                    batch_writes.append(
                        (deduplicate_table(enriched_table, key_columns), schema.name, "incremental_merge")
                    )
                elif cdc_table_mode == "cdc_only":
                    batch_writes.append(
                        (build_scd2_table(enriched_table, key_columns), f"{schema.name}_cdc", "scd2_append")
                    )
                elif cdc_table_mode == "both":
                    batch_writes.append(
                        (deduplicate_table(enriched_table, key_columns), schema.name, "incremental_merge")
                    )
                    batch_writes.append(
                        (build_scd2_table(enriched_table, key_columns), f"{schema.name}_cdc", "scd2_append")
                    )

                for write_table, write_resource_name, cdc_write_mode in batch_writes:
                    tracker = _get_or_create_tracker(
                        table_name,
                        write_resource_name,
                        cdc_write_mode,
                        cdc_table_mode,
                        key_columns,
                        schema,
                    )
                    batch_result = tracker.s3_writer.write_batch(write_table, batch_index=tracker.batch_index)
                    tracker.batch_results.append(batch_result)
                    tracker.batch_index += 1
                    tracker.total_rows += write_table.num_rows
                    flushed.add(write_resource_name)

                    log.info(
                        "cdc_batch_written",
                        table=table_name,
                        resource=write_resource_name,
                        rows=write_table.num_rows,
                        batch_index=tracker.batch_index - 1,
                        s3_path=batch_result.s3_path,
                    )

                    # Dispatch immediately so progress survives process failures.
                    if schema.cdc_mode == "streaming":
                        _send_kafka_batch(tracker, batch_result, is_final_batch=is_final)
                    elif schema.cdc_mode == "snapshot":
                        _store_deferred_batch(tracker, batch_result, schema)

            return flushed

        # ------------------------------------------------------------------
        # 1. Read WAL events with periodic micro-batch flushes.
        #    Streaming schemas get Kafka messages immediately after each S3 write.
        # ------------------------------------------------------------------
        batcher = ChangeEventBatcher()
        last_end_lsn: str | None = None
        event_count = 0
        all_table_names: set[str] = set()

        for event in reader.read_changes():
            activity.heartbeat()

            # The publication should be scoped to CDC-enabled tables only, so in
            # practice this filter is a no-op. It's a safety net in case the
            # publication includes extra tables (e.g. self-managed mode).
            if event.table_name not in cdc_table_names:
                continue

            batcher.add(event)
            last_end_lsn = event.position_serialized
            event_count += 1

            if batcher.should_flush:
                tables = batcher.flush()
                all_table_names.update(tables.keys())
                _process_flush(tables, is_final=False)
                log.info("cdc_micro_batch_flushed", events_so_far=event_count, trackers=len(write_trackers))

        # Capture remaining table names before final flush
        all_table_names.update(batcher.table_names)

        log.info("wal_changes_read", event_count=event_count, tables=list(all_table_names))

        # ------------------------------------------------------------------
        # 2. Post-WAL: PK change detection, truncate handling
        # ------------------------------------------------------------------
        for table_name in all_table_names:
            decoder_pks = reader.get_decoder_key_columns(table_name)
            stored_pks = pk_columns_by_table.get(table_name, [])
            if decoder_pks and decoder_pks != stored_pks:
                log.warning("pk_columns_changed", table=table_name, old=stored_pks, new=decoder_pks)
                pk_columns_by_table[table_name] = decoder_pks
                pk_schema = schema_by_name.get(table_name)
                if pk_schema is not None:
                    pk_schema.sync_type_config["primary_key_columns"] = decoder_pks
                    pk_schema.save(update_fields=["sync_type_config", "updated_at"])

        truncated_tables = list(reader.truncated_tables)
        reader.clear_truncated_tables()
        for table_name in truncated_tables:
            trunc_schema = schema_by_name.get(table_name)
            if trunc_schema is not None:
                log.warning("truncate_detected", table=table_name, schema_id=str(trunc_schema.id))
                trunc_schema.sync_type_config["cdc_mode"] = "snapshot"
                trunc_schema.sync_type_config.pop("cdc_last_log_position", None)
                trunc_schema.initial_sync_complete = False
                trunc_schema.save(update_fields=["sync_type_config", "initial_sync_complete", "updated_at"])
                try:
                    from products.data_warehouse.backend.data_load.service import unpause_external_data_schedule

                    unpause_external_data_schedule(str(trunc_schema.id))
                    log.info("unpaused_schema_schedule_for_resnapshot", schema_id=str(trunc_schema.id))
                except Exception:
                    log.warning("failed_to_unpause_schema_schedule", schema_id=str(trunc_schema.id))

        if event_count == 0:
            if truncated_tables:
                truncate_end_lsn = reader.last_commit_end_lsn
                if truncate_end_lsn is not None:
                    reader.confirm_position(truncate_end_lsn)
                    log.info("slot_advanced_past_truncate", position=truncate_end_lsn)
            now = dt.datetime.now(tz=dt.UTC)
            for schema in cdc_schemas:
                schema.status = ExternalDataSchema.Status.COMPLETED
                schema.latest_error = None
                schema.last_synced_at = now
                schema.save(update_fields=["status", "latest_error", "last_synced_at", "updated_at"])
            log.info("no_wal_changes")
            return

        # ------------------------------------------------------------------
        # 3. Flush deferred runs for schemas that transitioned to streaming
        # ------------------------------------------------------------------
        for schema in cdc_schemas:
            if schema.cdc_mode == "streaming" and schema.sync_type_config.get("cdc_deferred_runs"):
                _flush_deferred_runs(schema, source, log)

        # ------------------------------------------------------------------
        # 4. Final flush: remaining buffered events get is_final_batch=True
        # ------------------------------------------------------------------
        final_flushed: set[str] = set()
        if batcher.event_count > 0:
            tables = batcher.flush()
            final_flushed = _process_flush(tables, is_final=True)

        # ------------------------------------------------------------------
        # 5. Finalize trackers.
        #    - Streaming trackers that had no data in the final flush need an
        #      empty finalization batch so the consumer triggers post-load ops.
        #    - Snapshot trackers: batch results were already persisted to
        #      sync_type_config by _store_deferred_batch; write schema file
        #      and update the deferred entry with the final schema_path.
        # ------------------------------------------------------------------
        for resource_name, tracker in write_trackers.items():
            schema = schema_by_name[tracker.table_name]

            if schema.cdc_mode == "streaming":
                if resource_name not in final_flushed:
                    # Write a zero-row parquet so the consumer has a valid s3_path to
                    # read.  It processes 0 rows (DeltaLake no-op) but still runs
                    # post-load ops and marks the job completed.
                    empty = pa.table({"_empty": pa.array([], type=pa.int8())})
                    finalize_result = tracker.s3_writer.write_batch(empty, batch_index=tracker.batch_index)
                    tracker.batch_index += 1
                    _send_kafka_batch(tracker, finalize_result, is_final_batch=True)

                tracker.job.rows_synced = tracker.total_rows
                tracker.job.save(update_fields=["rows_synced", "updated_at"])

            elif schema.cdc_mode == "snapshot":
                # Write schema file and update the deferred entry with final metadata.
                schema_path = tracker.s3_writer.write_schema()
                deferred = schema.sync_type_config.get("cdc_deferred_runs", [])
                for entry in deferred:
                    if entry.get("run_uuid") == tracker.run_uuid:
                        entry["schema_path"] = schema_path
                        entry["total_batches"] = tracker.batch_index
                        entry["total_rows"] = tracker.total_rows
                        break
                schema.save(update_fields=["sync_type_config", "updated_at"])

                tracker.job.rows_synced = tracker.total_rows
                tracker.job.status = ExternalDataJob.Status.COMPLETED
                tracker.job.finished_at = dt.datetime.now(tz=dt.UTC)
                tracker.job.save(update_fields=["rows_synced", "status", "finished_at", "updated_at"])

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
    close_old_connections()

    source = ExternalDataSource.objects.get(pk=inputs.source_id)
    adapter = get_cdc_adapter(source)

    return adapter.validate_prerequisites(
        source=source,
        management_mode=inputs.management_mode,  # type: ignore[arg-type]
        tables=inputs.tables,
        schema=inputs.schema,
        slot_name=inputs.slot_name,
        publication_name=inputs.publication_name,
    )


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
    close_old_connections()

    log = logger.bind()
    log.info("cleanup_orphan_slots_started")

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

        try:
            adapter = get_cdc_adapter(source)
        except ValueError:
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
                with adapter.management_connection(source, connect_timeout=10) as conn:
                    adapter.drop_resources(conn, slot_name, pub_name)
            except Exception:
                source_log.exception("failed_to_cleanup_deleted_source_slot")
            continue

        # 2. Active sources — check WAL lag
        if source.deleted:
            continue

        try:
            with adapter.management_connection(source, connect_timeout=10) as conn:
                lag_bytes = adapter.get_lag_bytes(conn, slot_name)
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
                    with adapter.management_connection(source, connect_timeout=10) as conn:
                        adapter.drop_resources(conn, slot_name, pub_name)

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
