from dataclasses import asdict

from django.conf import settings

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
)

from posthog.temporal.anomalies.types import ScheduleScoringInputs, ScheduleTrainingInputs
from posthog.temporal.common.schedule import a_create_schedule, a_schedule_exists, a_update_schedule

TRAINING_SCHEDULE_ID = "train-anomalies-schedule"
SCORING_SCHEDULE_ID = "score-anomalies-schedule"


async def create_anomaly_training_schedule(client: Client) -> None:
    """Training schedule: runs hourly. Discovers insights and trains models."""
    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            "train-anomalies",
            asdict(ScheduleTrainingInputs()),
            id=TRAINING_SCHEDULE_ID,
            task_queue=settings.GENERAL_PURPOSE_TASK_QUEUE,
        ),
        spec=ScheduleSpec(cron_expressions=["0 * * * *"]),  # top of every hour
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
    )

    if await a_schedule_exists(client, TRAINING_SCHEDULE_ID):
        await a_update_schedule(client, TRAINING_SCHEDULE_ID, schedule)
    else:
        await a_create_schedule(client, TRAINING_SCHEDULE_ID, schedule, trigger_immediately=False)


async def create_anomaly_scoring_schedule(client: Client) -> None:
    """Scoring schedule: runs every 5 minutes. Scores latest data against trained models."""
    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            "score-anomalies",
            asdict(ScheduleScoringInputs()),
            id=SCORING_SCHEDULE_ID,
            task_queue=settings.GENERAL_PURPOSE_TASK_QUEUE,
        ),
        spec=ScheduleSpec(cron_expressions=["*/5 * * * *"]),
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
    )

    if await a_schedule_exists(client, SCORING_SCHEDULE_ID):
        await a_update_schedule(client, SCORING_SCHEDULE_ID, schedule)
    else:
        await a_create_schedule(client, SCORING_SCHEDULE_ID, schedule, trigger_immediately=False)
