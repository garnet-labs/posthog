import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleState

from posthog.temporal.common.client import sync_connect
from posthog.temporal.common.schedule import (
    create_schedule,
    delete_schedule,
    pause_schedule,
    schedule_exists,
    unpause_schedule,
    update_schedule,
)

from .models import Task, TaskAutomation, TaskRun

logger = logging.getLogger(__name__)


def build_automation_schedule(automation: TaskAutomation) -> Schedule:
    return Schedule(
        action=ScheduleActionStartWorkflow(
            "run-task-automation",
            str(automation.id),
            id=f'task-automation-run-{automation.id}-{{{{.ScheduledTime.Format "2006-01-02-15-04"}}}}',
            task_queue=settings.TASKS_TASK_QUEUE,
        ),
        spec=ScheduleSpec(
            cron_expressions=[automation.cron_expression],
            time_zone_name=automation.timezone,
        ),
        state=ScheduleState(
            paused=not automation.enabled,
            note=f"Schedule for task automation: {automation.id}",
        ),
    )


def sync_automation_schedule(automation: TaskAutomation) -> None:
    temporal = sync_connect()
    schedule = build_automation_schedule(automation)

    if schedule_exists(temporal, automation.schedule_id):
        update_schedule(temporal, automation.schedule_id, schedule)
        if automation.enabled:
            unpause_schedule(temporal, automation.schedule_id, note="Automation enabled")
        else:
            pause_schedule(temporal, automation.schedule_id, note="Automation paused")
    else:
        create_schedule(temporal, automation.schedule_id, schedule)


def delete_automation_schedule(automation: TaskAutomation) -> None:
    temporal = sync_connect()
    if schedule_exists(temporal, automation.schedule_id):
        delete_schedule(temporal, automation.schedule_id)


def run_task_automation(automation_id: str, trigger_workflow_id: str | None = None) -> tuple[Task, TaskRun]:
    automation_id = str(automation_id)
    with transaction.atomic():
        automation = TaskAutomation.objects.select_for_update().select_related("team", "task").get(id=automation_id)

        if trigger_workflow_id:
            existing_task_run_query = TaskRun.objects.select_related("task").filter(
                state__automation_id=automation_id,
                state__automation_trigger_workflow_id=trigger_workflow_id,
            )
            if automation.task_id:
                existing_task_run_query = existing_task_run_query.filter(task_id=automation.task_id)
            else:
                existing_task_run_query = existing_task_run_query.filter(
                    task__team_id=automation.team_id,
                    task__origin_product=Task.OriginProduct.AUTOMATION,
                )
            existing_task_run = existing_task_run_query.order_by("-created_at").first()
            if existing_task_run is not None:
                task = existing_task_run.task
                task_run = existing_task_run
            else:
                task = _get_or_create_automation_task(automation)
                extra_state = {"automation_id": automation_id}
                if trigger_workflow_id:
                    extra_state["automation_trigger_workflow_id"] = trigger_workflow_id
                task_run = task.create_run(mode="background", extra_state=extra_state)
        else:
            task = _get_or_create_automation_task(automation)
            task_run = task.create_run(mode="background", extra_state={"automation_id": automation_id})

        team_id = automation.team_id
        user_id = automation.created_by_id

        automation.last_run_at = timezone.now()
        automation.last_run_status = TaskAutomation.RunStatus.RUNNING
        automation.last_task_run = task_run
        automation.last_error = None
        automation.save(
            update_fields=[
                "task",
                "last_run_at",
                "last_run_status",
                "last_task_run",
                "last_error",
                "updated_at",
            ]
        )

        transaction.on_commit(
            lambda: execute_task_processing_workflow_for_automation(
                team_id=team_id,
                user_id=user_id,
                task_id=str(task.id),
                run_id=str(task_run.id),
            )
        )

    logger.info(
        "task_automation_run_started",
        extra={
            "automation_id": automation_id,
            "task_id": str(task.id),
            "run_id": str(task_run.id),
            "team_id": team_id,
        },
    )

    return task, task_run


def _get_or_create_automation_task(automation: TaskAutomation) -> Task:
    task = automation.task
    if task is None:
        task = Task.objects.create(
            team=automation.team,
            created_by=automation.created_by,
            title=automation.name,
            description=automation.prompt,
            origin_product=Task.OriginProduct.AUTOMATION,
            github_integration=automation.github_integration,
            repository=automation.repository,
        )
        automation.task = task
        return task

    fields_to_update: list[str] = []
    if task.title != automation.name:
        task.title = automation.name
        fields_to_update.append("title")
    if task.description != automation.prompt:
        task.description = automation.prompt
        fields_to_update.append("description")
    if task.github_integration_id != automation.github_integration_id:
        task.github_integration = automation.github_integration
        fields_to_update.append("github_integration")
    if task.repository != automation.repository:
        task.repository = automation.repository
        fields_to_update.append("repository")

    if fields_to_update:
        fields_to_update.append("updated_at")
        task.save(update_fields=fields_to_update)

    return task


def execute_task_processing_workflow_for_automation(
    *, team_id: int, user_id: int | None, task_id: str, run_id: str
) -> None:
    from .temporal.client import execute_task_processing_workflow

    execute_task_processing_workflow(
        task_id=task_id,
        run_id=run_id,
        team_id=team_id,
        user_id=user_id,
        skip_user_check=True,
    )


def update_automation_run_result(task_run: TaskRun) -> None:
    if task_run.task.origin_product != Task.OriginProduct.AUTOMATION:
        return

    automation = TaskAutomation.objects.filter(last_task_run=task_run).first()
    if automation is None:
        return

    if task_run.status == TaskRun.Status.COMPLETED:
        status = TaskAutomation.RunStatus.SUCCESS
        error = None
    elif task_run.status in [TaskRun.Status.FAILED, TaskRun.Status.CANCELLED]:
        status = TaskAutomation.RunStatus.FAILED
        error = task_run.error_message
    else:
        status = TaskAutomation.RunStatus.RUNNING
        error = None

    automation.last_run_status = status
    automation.last_error = error
    automation.save(update_fields=["last_run_status", "last_error", "updated_at"])
