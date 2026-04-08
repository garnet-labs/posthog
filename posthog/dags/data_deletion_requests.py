import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial

from django.conf import settings as django_settings

import dagster
import pydantic
from clickhouse_driver import Client

from posthog.clickhouse.cluster import (
    AlterTableMutationRunner,
    ClickhouseCluster,
    LightweightDeleteMutationRunner,
    Query,
)
from posthog.dags.common import JobOwners
from posthog.models.data_deletion_request import DataDeletionRequest, RequestStatus, RequestType
from posthog.models.event.sql import EVENTS_DATA_TABLE

OWNER_TAG = {"owner": JobOwners.TEAM_CLICKHOUSE.value}


class DataDeletionRequestConfig(dagster.Config):
    request_id: str = pydantic.Field(description="UUID of the DataDeletionRequest to execute.")


@dataclass
class DeletionRequestContext:
    request_id: str
    team_id: int
    start_time: datetime
    end_time: datetime
    events: list[str]
    properties: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _temp_table_name(request_id: str) -> str:
    return f"tmp_prop_rm_{request_id[:8]}"


def _property_filter_clause(properties: list[str]) -> str:
    if len(properties) == 1:
        return "JSONHas(properties, %(filter_property)s)"
    return "hasAny(JSONExtractKeys(properties), %(filter_properties)s)"


def _property_filter_params(properties: list[str]) -> dict:
    if len(properties) == 1:
        return {"filter_property": properties[0]}
    return {"filter_properties": properties}


def _base_params(ctx: DeletionRequestContext) -> dict:
    return {
        "team_id": ctx.team_id,
        "start_time": ctx.start_time,
        "end_time": ctx.end_time,
        "events": ctx.events,
        **_property_filter_params(ctx.properties),
    }


def _create_local_staging_table(client: Client, source_table: str, staging_table: str) -> None:
    """Create a non-replicated local copy of the source table schema."""
    database = django_settings.CLICKHOUSE_DATABASE

    rows = client.execute(
        "SELECT count() FROM system.tables WHERE database = %(db)s AND name = %(table)s",
        {"db": database, "table": staging_table},
    )
    if rows[0][0] > 0:
        return

    rows = client.execute(
        "SELECT engine_full FROM system.tables WHERE database = %(db)s AND name = %(table)s",
        {"db": database, "table": source_table},
    )
    if not rows:
        raise dagster.Failure(description=f"Source table {database}.{source_table} not found")

    engine_full = rows[0][0]

    def _strip_replication(m: re.Match) -> str:
        base_engine = m.group(1)
        extra_args = m.group(2)
        if base_engine == "MergeTree" or not extra_args:
            return f"{base_engine}()"
        return f"{base_engine}({extra_args})"

    engine_clause, count = re.subn(
        r"Replicated(\w+)\('[^']*',\s*'\{replica\}'(?:,\s*(.+?))?\)",
        _strip_replication,
        engine_full,
        count=1,
    )
    if count == 0:
        raise dagster.Failure(
            description=f"Source table {source_table} does not use a Replicated engine: {engine_full}"
        )

    client.execute(
        f"CREATE TABLE IF NOT EXISTS {database}.{staging_table} AS {database}.{source_table} ENGINE = {engine_clause}"
    )


# ---------------------------------------------------------------------------
# Event removal ops (unchanged)
# ---------------------------------------------------------------------------


@dagster.op(tags=OWNER_TAG)
def load_deletion_request(
    context: dagster.OpExecutionContext,
    config: DataDeletionRequestConfig,
) -> DeletionRequestContext:
    """Load and validate the deletion request, transition to IN_PROGRESS."""
    from django.db import transaction

    with transaction.atomic():
        request = (
            DataDeletionRequest.objects.select_for_update()
            .filter(
                pk=config.request_id,
                status=RequestStatus.APPROVED,
                request_type=RequestType.EVENT_REMOVAL,
            )
            .first()
        )

        if not request:
            raise dagster.Failure(
                f"Request {config.request_id} is not an approved event_removal request.",
            )

        request.status = RequestStatus.IN_PROGRESS
        request.save(update_fields=["status", "updated_at"])

    context.log.info(
        f"Processing deletion request {request.pk}: "
        f"team_id={request.team_id}, events={request.events}, "
        f"time_range={request.start_time} to {request.end_time}"
    )
    context.add_output_metadata(
        {
            "team_id": dagster.MetadataValue.int(request.team_id),
            "events": dagster.MetadataValue.text(", ".join(request.events)),
            "start_time": dagster.MetadataValue.text(str(request.start_time)),
            "end_time": dagster.MetadataValue.text(str(request.end_time)),
        }
    )

    return DeletionRequestContext(
        request_id=str(request.pk),
        team_id=request.team_id,
        start_time=request.start_time,
        end_time=request.end_time,
        events=request.events,
    )


@dagster.op(tags=OWNER_TAG)
def execute_event_deletion(
    context: dagster.OpExecutionContext,
    cluster: dagster.ResourceParam[ClickhouseCluster],
    deletion_request: DeletionRequestContext,
) -> DeletionRequestContext:
    """Execute lightweight deletes on each shard serially."""
    table = EVENTS_DATA_TABLE()
    shards = sorted(cluster.shards)
    total_shards = len(shards)

    context.log.info(f"Starting event deletion across {total_shards} shards on table {table}")

    for idx, shard_num in enumerate(shards, 1):
        context.log.info(f"Processing shard {shard_num} ({idx}/{total_shards})")
        shard_start = time.monotonic()

        runner = LightweightDeleteMutationRunner(
            table=table,
            predicate=(
                "team_id = %(team_id)s "
                "AND timestamp >= %(start_time)s "
                "AND timestamp < %(end_time)s "
                "AND event IN %(events)s"
            ),
            parameters={
                "team_id": deletion_request.team_id,
                "start_time": deletion_request.start_time,
                "end_time": deletion_request.end_time,
                "events": deletion_request.events,
            },
            settings={"lightweight_deletes_sync": 0},
        )

        shard_result = cluster.map_any_host_in_shards({shard_num: runner}).result()
        _host, mutation_waiter = next(iter(shard_result.items()))
        cluster.map_all_hosts_in_shard(shard_num, mutation_waiter.wait).result()

        elapsed = time.monotonic() - shard_start
        context.log.info(f"Shard {shard_num} complete in {elapsed:.1f}s")

    context.add_output_metadata(
        {
            "shards_processed": dagster.MetadataValue.int(total_shards),
            "table": dagster.MetadataValue.text(table),
        }
    )

    return deletion_request


# ---------------------------------------------------------------------------
# Property removal ops
# ---------------------------------------------------------------------------


@dagster.op(tags=OWNER_TAG)
def load_property_removal_request(
    context: dagster.OpExecutionContext,
    config: DataDeletionRequestConfig,
) -> DeletionRequestContext:
    """Load and validate a property removal request, transition to IN_PROGRESS."""
    from django.db import transaction

    with transaction.atomic():
        request = (
            DataDeletionRequest.objects.select_for_update()
            .filter(
                pk=config.request_id,
                status=RequestStatus.APPROVED,
                request_type=RequestType.PROPERTY_REMOVAL,
            )
            .first()
        )

        if not request:
            raise dagster.Failure(
                f"Request {config.request_id} is not an approved property_removal request.",
            )

        if not request.properties:
            raise dagster.Failure(
                f"Request {config.request_id} has no properties specified.",
            )

        request.status = RequestStatus.IN_PROGRESS
        request.save(update_fields=["status", "updated_at"])

    context.log.info(
        f"Processing property removal {request.pk}: "
        f"team_id={request.team_id}, events={request.events}, "
        f"properties={request.properties}, "
        f"time_range={request.start_time} to {request.end_time}"
    )
    context.add_output_metadata(
        {
            "team_id": dagster.MetadataValue.int(request.team_id),
            "events": dagster.MetadataValue.text(", ".join(request.events)),
            "properties": dagster.MetadataValue.text(", ".join(request.properties)),
            "start_time": dagster.MetadataValue.text(str(request.start_time)),
            "end_time": dagster.MetadataValue.text(str(request.end_time)),
        }
    )

    return DeletionRequestContext(
        request_id=str(request.pk),
        team_id=request.team_id,
        start_time=request.start_time,
        end_time=request.end_time,
        events=request.events,
        properties=request.properties,
    )


@dagster.op(tags=OWNER_TAG)
def create_temp_tables(
    context: dagster.OpExecutionContext,
    cluster: dagster.ResourceParam[ClickhouseCluster],
    deletion_request: DeletionRequestContext,
) -> DeletionRequestContext:
    """Create a non-replicated local temp table on each shard."""
    source = EVENTS_DATA_TABLE()
    temp = _temp_table_name(deletion_request.request_id)

    for shard_num in sorted(cluster.shards):
        context.log.info(f"Creating temp table {temp} on shard {shard_num}")
        cluster.map_any_host_in_shards(
            {shard_num: partial(_create_local_staging_table, source_table=source, staging_table=temp)}
        ).result()

    return deletion_request


@dagster.op(tags=OWNER_TAG)
def copy_events_to_temp(
    context: dagster.OpExecutionContext,
    cluster: dagster.ResourceParam[ClickhouseCluster],
    deletion_request: DeletionRequestContext,
) -> DeletionRequestContext:
    """Copy matching events into the temp table on each shard (truncate first for idempotency)."""
    source = EVENTS_DATA_TABLE()
    temp = _temp_table_name(deletion_request.request_id)
    db = django_settings.CLICKHOUSE_DATABASE
    prop_filter = _property_filter_clause(deletion_request.properties)
    params = _base_params(deletion_request)

    for shard_num in sorted(cluster.shards):
        context.log.info(f"Copying events to temp on shard {shard_num}")

        def truncate_and_copy(client: Client) -> int:
            client.execute(f"TRUNCATE TABLE IF EXISTS {db}.{temp}")
            client.execute(
                f"""
                INSERT INTO {db}.{temp}
                SELECT * FROM {db}.{source}
                WHERE team_id = %(team_id)s
                  AND timestamp >= %(start_time)s
                  AND timestamp < %(end_time)s
                  AND event IN %(events)s
                  AND {prop_filter}
                """,
                params,
                settings={"max_execution_time": 1800},
            )
            result = client.execute(f"SELECT count() FROM {db}.{temp}")
            return result[0][0]

        count = cluster.map_any_host_in_shards({shard_num: truncate_and_copy}).result()
        _host, row_count = next(iter(count.items()))
        context.log.info(f"Shard {shard_num}: copied {row_count} events")

    return deletion_request


@dagster.op(tags=OWNER_TAG)
def mutate_temp_properties(
    context: dagster.OpExecutionContext,
    cluster: dagster.ResourceParam[ClickhouseCluster],
    deletion_request: DeletionRequestContext,
) -> DeletionRequestContext:
    """Run ALTER TABLE UPDATE on each temp table to drop the target properties."""
    temp = _temp_table_name(deletion_request.request_id)

    for shard_num in sorted(cluster.shards):
        context.log.info(f"Mutating properties on shard {shard_num}")
        shard_start = time.monotonic()

        runner = AlterTableMutationRunner(
            table=temp,
            commands={"UPDATE properties = JSONDropKeys(%(keys)s)(properties), inserted_at = now() WHERE 1=1"},
            parameters={"keys": deletion_request.properties},
        )

        shard_result = cluster.map_any_host_in_shards({shard_num: runner}).result()
        _host, waiter = next(iter(shard_result.items()))
        # Temp table is local (not replicated), so wait on the same host
        cluster.map_any_host_in_shards({shard_num: waiter.wait}).result()

        elapsed = time.monotonic() - shard_start
        context.log.info(f"Shard {shard_num}: mutation complete in {elapsed:.1f}s")

    return deletion_request


@dagster.op(tags=OWNER_TAG)
def verify_temp_mutations(
    context: dagster.OpExecutionContext,
    cluster: dagster.ResourceParam[ClickhouseCluster],
    deletion_request: DeletionRequestContext,
) -> DeletionRequestContext:
    """Verify that no target properties remain in the temp tables."""
    temp = _temp_table_name(deletion_request.request_id)
    db = django_settings.CLICKHOUSE_DATABASE
    prop_filter = _property_filter_clause(deletion_request.properties)
    params = _property_filter_params(deletion_request.properties)

    for shard_num in sorted(cluster.shards):
        result = cluster.map_any_host_in_shards(
            {shard_num: Query(f"SELECT count() FROM {db}.{temp} WHERE {prop_filter}", params)}
        ).result()
        _host, rows = next(iter(result.items()))
        remaining = rows[0][0]
        if remaining > 0:
            raise dagster.Failure(f"Shard {shard_num}: {remaining} events still have target properties after mutation.")
        context.log.info(f"Shard {shard_num}: verified, 0 events with target properties")

    return deletion_request


@dagster.op(tags=OWNER_TAG)
def insert_modified_events(
    context: dagster.OpExecutionContext,
    cluster: dagster.ResourceParam[ClickhouseCluster],
    deletion_request: DeletionRequestContext,
) -> DeletionRequestContext:
    """Insert modified events from temp tables back into sharded_events (before deleting originals)."""
    source = EVENTS_DATA_TABLE()
    temp = _temp_table_name(deletion_request.request_id)
    db = django_settings.CLICKHOUSE_DATABASE

    for shard_num in sorted(cluster.shards):
        context.log.info(f"Inserting modified events on shard {shard_num}")
        cluster.map_any_host_in_shards(
            {
                shard_num: Query(
                    f"INSERT INTO {db}.{source} SELECT * FROM {db}.{temp}",
                    settings={"max_execution_time": "1800"},
                )
            }
        ).result()
        context.log.info(f"Shard {shard_num}: insert complete")

    return deletion_request


@dagster.op(tags=OWNER_TAG)
def delete_original_events(
    context: dagster.OpExecutionContext,
    cluster: dagster.ResourceParam[ClickhouseCluster],
    deletion_request: DeletionRequestContext,
) -> DeletionRequestContext:
    """Delete the original (unmodified) events that still have the target properties."""
    table = EVENTS_DATA_TABLE()
    prop_filter = _property_filter_clause(deletion_request.properties)

    for shard_num in sorted(cluster.shards):
        context.log.info(f"Deleting originals on shard {shard_num}")
        shard_start = time.monotonic()

        runner = LightweightDeleteMutationRunner(
            table=table,
            predicate=(
                f"team_id = %(team_id)s "
                f"AND timestamp >= %(start_time)s "
                f"AND timestamp < %(end_time)s "
                f"AND event IN %(events)s "
                f"AND {prop_filter}"
            ),
            parameters=_base_params(deletion_request),
            settings={"lightweight_deletes_sync": 0},
        )

        shard_result = cluster.map_any_host_in_shards({shard_num: runner}).result()
        _host, waiter = next(iter(shard_result.items()))
        cluster.map_all_hosts_in_shard(shard_num, waiter.wait).result()

        elapsed = time.monotonic() - shard_start
        context.log.info(f"Shard {shard_num}: delete complete in {elapsed:.1f}s")

    return deletion_request


@dagster.op(tags=OWNER_TAG)
def cleanup_temp_tables(
    context: dagster.OpExecutionContext,
    cluster: dagster.ResourceParam[ClickhouseCluster],
    deletion_request: DeletionRequestContext,
) -> DeletionRequestContext:
    """Drop the temp tables on all shards."""
    temp = _temp_table_name(deletion_request.request_id)
    db = django_settings.CLICKHOUSE_DATABASE

    for shard_num in sorted(cluster.shards):
        cluster.map_any_host_in_shards({shard_num: Query(f"DROP TABLE IF EXISTS {db}.{temp}")}).result()
        context.log.info(f"Shard {shard_num}: temp table dropped")

    return deletion_request


# ---------------------------------------------------------------------------
# Shared ops
# ---------------------------------------------------------------------------


@dagster.op(tags=OWNER_TAG)
def mark_deletion_complete(
    context: dagster.OpExecutionContext,
    deletion_request: DeletionRequestContext,
) -> None:
    """Mark the deletion request as completed."""
    from django.utils import timezone

    DataDeletionRequest.objects.filter(
        pk=deletion_request.request_id,
        status=RequestStatus.IN_PROGRESS,
    ).update(status=RequestStatus.COMPLETED, updated_at=timezone.now())

    context.log.info(f"Deletion request {deletion_request.request_id} marked as completed.")


@dagster.failure_hook()
def mark_deletion_failed(context: dagster.HookContext) -> None:
    """Mark the deletion request as failed if any op fails."""
    from django.utils import timezone

    run = context.instance.get_run_by_id(context.run_id)
    if run is None:
        return

    run_config = run.run_config
    if not isinstance(run_config, dict):
        return

    ops_config = run_config.get("ops", {})
    # Check both job types
    request_id = ops_config.get("load_deletion_request", {}).get("config", {}).get("request_id") or ops_config.get(
        "load_property_removal_request", {}
    ).get("config", {}).get("request_id")
    if not request_id:
        return

    DataDeletionRequest.objects.filter(
        pk=request_id,
        status=RequestStatus.IN_PROGRESS,
    ).update(status=RequestStatus.FAILED, updated_at=timezone.now())

    context.log.error(f"Deletion request {request_id} marked as failed.")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@dagster.job(tags=OWNER_TAG, hooks={mark_deletion_failed})
def data_deletion_request_event_removal():
    """Execute an approved event deletion request by running lightweight deletes shard by shard."""
    request = load_deletion_request()
    result = execute_event_deletion(request)
    mark_deletion_complete(result)


@dagster.job(tags=OWNER_TAG, hooks={mark_deletion_failed})
def data_deletion_request_property_removal():
    """Execute an approved property removal request: copy events, drop properties, swap back."""
    request = load_property_removal_request()
    request = create_temp_tables(request)
    request = copy_events_to_temp(request)
    request = mutate_temp_properties(request)
    request = verify_temp_mutations(request)
    request = insert_modified_events(request)
    request = delete_original_events(request)
    request = cleanup_temp_tables(request)
    mark_deletion_complete(request)
