import json
import asyncio
import datetime as dt

import temporalio.common
import temporalio.workflow

from posthog.temporal.anomalies.activities.cleanup import cleanup_anomaly_scores
from posthog.temporal.anomalies.activities.score import fetch_insights_due_for_scoring, score_insight
from posthog.temporal.anomalies.types import (
    CleanupScoresActivityInputs,
    ScheduleScoringInputs,
    ScoreInsightActivityInputs,
    ScoreInsightResult,
    ScoreInsightWorkflowInputs,
)
from posthog.temporal.common.base import PostHogWorkflow

RETRY_POLICY = temporalio.common.RetryPolicy(
    initial_interval=dt.timedelta(seconds=10),
    maximum_interval=dt.timedelta(minutes=5),
    maximum_attempts=3,
)


@temporalio.workflow.defn(name="score-anomalies")
class ScoreAnomaliesWorkflow(PostHogWorkflow):
    """Top-level scoring workflow: fetch due insights, fan out scoring, cleanup.

    Concurrency is controlled by max_concurrent — higher than training
    because scoring queries are much lighter (sparkline window vs full
    training window).
    """

    @staticmethod
    def parse_inputs(inputs: list[str]) -> ScheduleScoringInputs:
        if not inputs:
            return ScheduleScoringInputs()
        return ScheduleScoringInputs(**json.loads(inputs[0]))

    @temporalio.workflow.run
    async def run(self, inputs: ScheduleScoringInputs) -> None:
        # Step 1: Fetch insights due for scoring (must have trained model)
        due: list[ScoreInsightActivityInputs] = await temporalio.workflow.execute_activity(
            fetch_insights_due_for_scoring,
            inputs,
            start_to_close_timeout=dt.timedelta(minutes=5),
            retry_policy=RETRY_POLICY,
        )

        if not due:
            return

        # Step 2: Fan out with concurrency limit
        semaphore = asyncio.Semaphore(inputs.max_concurrent)

        async def _run_one(insight_input: ScoreInsightActivityInputs) -> ScoreInsightResult | BaseException:
            async with semaphore:
                try:
                    return await temporalio.workflow.execute_child_workflow(
                        ScoreInsightWorkflow.run,
                        ScoreInsightWorkflowInputs(
                            insight_id=insight_input.insight_id,
                            team_id=insight_input.team_id,
                            model_storage_key=insight_input.model_storage_key,
                            detector_config=insight_input.detector_config,
                        ),
                        id=f"score-insight-{insight_input.insight_id}",
                        parent_close_policy=temporalio.workflow.ParentClosePolicy.ABANDON,
                        execution_timeout=dt.timedelta(minutes=10),
                    )
                except Exception as e:
                    return e

        await asyncio.gather(*[_run_one(i) for i in due])

        # Step 3: Cleanup old scores
        await temporalio.workflow.execute_activity(
            cleanup_anomaly_scores,
            CleanupScoresActivityInputs(),
            start_to_close_timeout=dt.timedelta(minutes=5),
            retry_policy=RETRY_POLICY,
        )


@temporalio.workflow.defn(name="score-insight")
class ScoreInsightWorkflow(PostHogWorkflow):
    """Per-insight child workflow: score latest data against pre-trained model."""

    @staticmethod
    def parse_inputs(inputs: list[str]) -> ScoreInsightWorkflowInputs:
        return ScoreInsightWorkflowInputs(**json.loads(inputs[0]))

    @temporalio.workflow.run
    async def run(self, inputs: ScoreInsightWorkflowInputs) -> ScoreInsightResult:
        return await temporalio.workflow.execute_activity(
            score_insight,
            ScoreInsightActivityInputs(
                insight_id=inputs.insight_id,
                team_id=inputs.team_id,
                model_storage_key=inputs.model_storage_key,
                detector_config=inputs.detector_config,
            ),
            start_to_close_timeout=dt.timedelta(minutes=5),
            retry_policy=RETRY_POLICY,
        )
