import json
import asyncio
import datetime as dt

import temporalio.common
import temporalio.workflow

from posthog.temporal.anomalies.activities.discover import discover_anomaly_insights
from posthog.temporal.anomalies.activities.train import fetch_insights_needing_training, train_insight
from posthog.temporal.anomalies.types import (
    DiscoverInsightsActivityInputs,
    ScheduleTrainingInputs,
    TrainInsightActivityInputs,
    TrainInsightResult,
    TrainInsightWorkflowInputs,
)
from posthog.temporal.common.base import PostHogWorkflow

RETRY_POLICY = temporalio.common.RetryPolicy(
    initial_interval=dt.timedelta(seconds=10),
    maximum_interval=dt.timedelta(minutes=5),
    maximum_attempts=3,
)


@temporalio.workflow.defn(name="train-anomalies")
class TrainAnomaliesWorkflow(PostHogWorkflow):
    """Top-level training workflow: discover insights, fan out training.

    Concurrency is controlled by max_concurrent — child workflows are
    launched through a semaphore so at most N are hitting ClickHouse
    simultaneously.
    """

    @staticmethod
    def parse_inputs(inputs: list[str]) -> ScheduleTrainingInputs:
        if not inputs:
            return ScheduleTrainingInputs()
        return ScheduleTrainingInputs(**json.loads(inputs[0]))

    @temporalio.workflow.run
    async def run(self, inputs: ScheduleTrainingInputs) -> None:
        # Step 1: Discover new eligible insights
        await temporalio.workflow.execute_activity(
            discover_anomaly_insights,
            DiscoverInsightsActivityInputs(),
            start_to_close_timeout=dt.timedelta(minutes=5),
            retry_policy=RETRY_POLICY,
        )

        # Step 2: Fetch insights needing (re)training
        due: list[TrainInsightActivityInputs] = await temporalio.workflow.execute_activity(
            fetch_insights_needing_training,
            inputs,
            start_to_close_timeout=dt.timedelta(minutes=5),
            retry_policy=RETRY_POLICY,
        )

        if not due:
            return

        # Step 3: Fan out with concurrency limit
        semaphore = asyncio.Semaphore(inputs.max_concurrent)

        async def _run_one(insight_input: TrainInsightActivityInputs) -> TrainInsightResult | BaseException:
            async with semaphore:
                try:
                    return await temporalio.workflow.execute_child_workflow(
                        TrainInsightWorkflow.run,
                        TrainInsightWorkflowInputs(
                            insight_id=insight_input.insight_id,
                            team_id=insight_input.team_id,
                            detector_config=insight_input.detector_config,
                        ),
                        id=f"train-insight-{insight_input.insight_id}",
                        parent_close_policy=temporalio.workflow.ParentClosePolicy.ABANDON,
                        execution_timeout=dt.timedelta(minutes=15),
                    )
                except Exception as e:
                    return e

        await asyncio.gather(*[_run_one(i) for i in due])


@temporalio.workflow.defn(name="train-insight")
class TrainInsightWorkflow(PostHogWorkflow):
    """Per-insight child workflow: train models for all series."""

    @staticmethod
    def parse_inputs(inputs: list[str]) -> TrainInsightWorkflowInputs:
        return TrainInsightWorkflowInputs(**json.loads(inputs[0]))

    @temporalio.workflow.run
    async def run(self, inputs: TrainInsightWorkflowInputs) -> TrainInsightResult:
        return await temporalio.workflow.execute_activity(
            train_insight,
            TrainInsightActivityInputs(
                insight_id=inputs.insight_id,
                team_id=inputs.team_id,
                detector_config=inputs.detector_config,
            ),
            start_to_close_timeout=dt.timedelta(minutes=10),
            retry_policy=RETRY_POLICY,
        )
