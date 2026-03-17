from __future__ import annotations

import json
import datetime as dt

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from posthog.temporal.common.base import PostHogWorkflow

with workflow.unsafe.imports_passed_through():
    from posthog.temporal.common.logger import get_logger
    from posthog.temporal.ducklake.duckling_backfill_inputs import (
        DucklingBackfillInputs,
        DucklingCopyFilesInputs,
        DucklingCopyFilesResult,
        DucklingDiscoveryInputs,
        DucklingDiscoveryResult,
        DucklingRegisterInputs,
        DucklingResolveConfigInputs,
        DucklingResolveConfigResult,
        DucklingUpdateStatusInputs,
    )

LOGGER = get_logger(__name__)

ACTIVITY_RETRY_POLICY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=dt.timedelta(seconds=10),
)


@workflow.defn(name="duckling-backfill")
class DucklingBackfillWorkflow(PostHogWorkflow):
    """Backfill a single team/partition from the shared DuckLake to a customer's duckling.

    Steps:
    1. Update status to running
    2. Resolve duckling config (catalog + IAM role assumption)
    3. Copy partition files from shared DuckLake to customer S3 via S3 CopyObject
    4. Register Parquet files with customer's DuckLake catalog via duckgres
    5. Update status to completed
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

        logger = LOGGER.bind(**inputs.properties_to_log)
        workflow_id = workflow.info().workflow_id

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


@workflow.defn(name="duckling-backfill-discovery")
class DucklingBackfillDiscoveryWorkflow(PostHogWorkflow):
    """Discovery workflow that finds teams needing backfill and spawns child workflows.

    Runs hourly and:
    1. Discovers teams that haven't completed yesterday's backfill
    2. Spawns a child DucklingBackfillWorkflow for each with ABANDON parent close policy
    """

    @staticmethod
    def parse_inputs(inputs: list[str]) -> DucklingDiscoveryInputs:
        loaded = json.loads(inputs[0])
        return DucklingDiscoveryInputs(**loaded)

    @workflow.run
    async def run(self, inputs: DucklingDiscoveryInputs) -> None:
        logger = LOGGER.bind(**inputs.properties_to_log)
        logger.info("Starting duckling backfill discovery")

        results: list[DucklingDiscoveryResult] = await workflow.execute_activity(
            "discover_duckling_teams_activity",
            inputs,
            result_type=list[DucklingDiscoveryResult],
            start_to_close_timeout=dt.timedelta(minutes=5),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        if not results:
            logger.info("No teams need backfill")
            return

        logger.info("Spawning child workflows", count=len(results))

        started = 0
        skipped = 0
        for result in results:
            child_workflow_id = f"duckling-backfill-{inputs.data_type}-{result.team_id}-{result.partition_key}"

            try:
                await workflow.start_child_workflow(
                    "duckling-backfill",
                    DucklingBackfillInputs(
                        team_id=result.team_id,
                        data_type=inputs.data_type,
                        partition_key=result.partition_key,
                    ),
                    id=child_workflow_id,
                    parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                    retry_policy=RetryPolicy(
                        maximum_attempts=3,
                        initial_interval=dt.timedelta(minutes=1),
                    ),
                )
                started += 1
            except WorkflowAlreadyStartedError:
                skipped += 1

        logger.info("Discovery complete", started=started, skipped=skipped)
