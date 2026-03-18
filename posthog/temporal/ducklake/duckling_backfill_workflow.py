from __future__ import annotations

import json
import datetime as dt

from temporalio import workflow
from temporalio.common import RetryPolicy

from posthog.temporal.common.base import PostHogWorkflow

with workflow.unsafe.imports_passed_through():
    from posthog.temporal.common.logger import get_logger
    from posthog.temporal.ducklake.duckling_backfill_inputs import (
        DucklingBackfillInputs,
        DucklingCheckAutoPauseInputs,
        DucklingCopyFilesInputs,
        DucklingCopyFilesResult,
        DucklingRegisterInputs,
        DucklingResolveConfigInputs,
        DucklingResolveConfigResult,
        DucklingUpdateStatusInputs,
    )

LOGGER = get_logger(__name__)

# Unlimited retries bounded by workflow execution timeout (matching batch exports)
ACTIVITY_RETRY_POLICY = RetryPolicy(
    maximum_attempts=0,
    initial_interval=dt.timedelta(seconds=30),
    maximum_interval=dt.timedelta(minutes=2),
)


def _get_partition_key_from_schedule() -> str:
    """Derive the partition date from Temporal's TemporalScheduledStartTime.

    The scheduled start time is when the schedule fired. We subtract one day
    to get yesterday's partition (the data we're backfilling).
    Falls back to yesterday relative to workflow.now() if not on a schedule.
    """
    search_attr = workflow.info().search_attributes.get("TemporalScheduledStartTime")

    if search_attr and search_attr[0]:
        if isinstance(search_attr[0], dt.datetime):
            scheduled_time = search_attr[0]
        elif isinstance(search_attr[0], str):
            scheduled_time = dt.datetime.fromisoformat(search_attr[0])
        else:
            scheduled_time = workflow.now()
    else:
        scheduled_time = workflow.now()

    partition_date = scheduled_time - dt.timedelta(days=1)
    return partition_date.strftime("%Y-%m-%d")


@workflow.defn(name="duckling-backfill")
class DucklingBackfillWorkflow(PostHogWorkflow):
    """Backfill a single team/partition from the shared DuckLake to a customer's duckling.

    Fired directly by a per-team Temporal schedule (one per team + data_type).
    The partition date is derived from TemporalScheduledStartTime so Temporal
    handles missed-day buffering automatically.

    Steps:
    1. Derive partition_key from schedule (or use explicit value)
    2. Check auto-pause threshold — skip if too many recent failures
    3. Update status to running
    4. Resolve duckling config (catalog + IAM role assumption)
    5. Copy partition files from shared DuckLake to customer S3 via S3 CopyObject
    6. Register Parquet files with customer's DuckLake catalog via duckgres
    7. Update status to completed
    """

    @staticmethod
    def parse_inputs(inputs: list[str]) -> DucklingBackfillInputs:
        loaded = json.loads(inputs[0])
        return DucklingBackfillInputs(**loaded)

    @workflow.run
    async def run(self, inputs: DucklingBackfillInputs) -> None:
        from posthog.temporal.ducklake.duckling_backfill_inputs import VALID_DATA_TYPES

        if inputs.data_type not in VALID_DATA_TYPES:
            raise ValueError(f"Invalid data_type: {inputs.data_type}, must be one of {VALID_DATA_TYPES}")

        # Derive partition_key from Temporal's scheduled time if not set explicitly
        if not inputs.partition_key:
            inputs.partition_key = _get_partition_key_from_schedule()

        logger = LOGGER.bind(**inputs.properties_to_log)
        workflow_id = workflow.info().workflow_id

        # Check auto-pause before doing any work
        is_paused: bool = await workflow.execute_activity(
            "check_auto_pause_activity",
            DucklingCheckAutoPauseInputs(
                team_id=inputs.team_id,
                data_type=inputs.data_type,
            ),
            start_to_close_timeout=dt.timedelta(seconds=30),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        if is_paused:
            logger.warning("Team is auto-paused due to failure threshold, skipping")
            return

        logger.info("Starting duckling backfill workflow")

        # Mark as running
        await workflow.execute_activity(
            "update_backfill_run_status_activity",
            DucklingUpdateStatusInputs(
                team_id=inputs.team_id,
                data_type=inputs.data_type,
                partition_key=inputs.partition_key,
                status="running",
                workflow_id=workflow_id,
            ),
            start_to_close_timeout=dt.timedelta(seconds=30),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        try:
            # Resolve duckling config (get customer S3 credentials)
            config_result: DucklingResolveConfigResult = await workflow.execute_activity(
                "resolve_duckling_config_activity",
                DucklingResolveConfigInputs(
                    team_id=inputs.team_id,
                    data_type=inputs.data_type,
                ),
                result_type=DucklingResolveConfigResult,
                start_to_close_timeout=dt.timedelta(minutes=2),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )

            # Copy partition files from shared DuckLake to customer S3
            copy_result: DucklingCopyFilesResult = await workflow.execute_activity(
                "copy_partition_files_activity",
                DucklingCopyFilesInputs(
                    team_id=inputs.team_id,
                    data_type=inputs.data_type,
                    partition_key=inputs.partition_key,
                    dest_bucket=config_result.bucket,
                    dest_region=config_result.region,
                    aws_access_key_id=config_result.aws_access_key_id,
                    aws_secret_access_key=config_result.aws_secret_access_key,
                    aws_session_token=config_result.aws_session_token,
                ),
                result_type=DucklingCopyFilesResult,
                start_to_close_timeout=dt.timedelta(minutes=30),
                heartbeat_timeout=dt.timedelta(minutes=5),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )

            if not copy_result.dest_s3_paths:
                logger.info("No files to copy, marking as completed")
                await workflow.execute_activity(
                    "update_backfill_run_status_activity",
                    DucklingUpdateStatusInputs(
                        team_id=inputs.team_id,
                        data_type=inputs.data_type,
                        partition_key=inputs.partition_key,
                        status="completed",
                        workflow_id=workflow_id,
                        records_exported=0,
                        bytes_exported=0,
                    ),
                    start_to_close_timeout=dt.timedelta(seconds=30),
                    retry_policy=ACTIVITY_RETRY_POLICY,
                )
                return

            # Register the files with the customer's DuckLake catalog via duckgres
            await workflow.execute_activity(
                "register_with_ducklake_activity",
                DucklingRegisterInputs(
                    team_id=inputs.team_id,
                    data_type=inputs.data_type,
                    s3_paths=copy_result.dest_s3_paths,
                ),
                start_to_close_timeout=dt.timedelta(minutes=10),
                heartbeat_timeout=dt.timedelta(minutes=3),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )

            # Mark as completed
            await workflow.execute_activity(
                "update_backfill_run_status_activity",
                DucklingUpdateStatusInputs(
                    team_id=inputs.team_id,
                    data_type=inputs.data_type,
                    partition_key=inputs.partition_key,
                    status="completed",
                    workflow_id=workflow_id,
                    records_exported=copy_result.total_records,
                    bytes_exported=copy_result.total_bytes,
                ),
                start_to_close_timeout=dt.timedelta(seconds=30),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )

            logger.info(
                "Duckling backfill completed",
                records=copy_result.total_records,
                bytes=copy_result.total_bytes,
                files=len(copy_result.dest_s3_paths),
            )

        except Exception as e:
            logger.exception("Duckling backfill failed", error=str(e))

            # Mark as failed
            await workflow.execute_activity(
                "update_backfill_run_status_activity",
                DucklingUpdateStatusInputs(
                    team_id=inputs.team_id,
                    data_type=inputs.data_type,
                    partition_key=inputs.partition_key,
                    status="failed",
                    workflow_id=workflow_id,
                    error_message=str(e)[:1000],
                ),
                start_to_close_timeout=dt.timedelta(seconds=30),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
            raise
