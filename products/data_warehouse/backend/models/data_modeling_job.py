from django.db import models
from django.utils import timezone

from posthog.models.utils import CreatedMetaFields, UpdatedMetaFields, UUIDTModel


class DataModelingJobStatus(models.TextChoices):
    CANCELLED = "Cancelled", "Cancelled"
    COMPLETED = "Completed", "Completed"
    FAILED = "Failed", "Failed"
    QUEUED = "Queued", "Queued"
    RUNNING = "Running", "Running"


class DataModelingJob(CreatedMetaFields, UpdatedMetaFields, UUIDTModel):
    Status = DataModelingJobStatus

    team = models.ForeignKey("posthog.Team", on_delete=models.SET_NULL, null=True)
    saved_query = models.ForeignKey("data_warehouse.DataWarehouseSavedQuery", on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=400, choices=Status.choices, default=Status.RUNNING)
    rows_materialized = models.IntegerField(default=0)
    error = models.TextField(null=True, blank=True)
    workflow_id = models.CharField(max_length=400, null=True, blank=True)
    workflow_run_id = models.CharField(max_length=400, null=True, blank=True)
    last_run_at = models.DateTimeField(default=timezone.now)
    rows_expected = models.IntegerField(null=True, blank=True, help_text="Total rows expected to be materialized")
    storage_delta_mib = models.FloatField(null=True, blank=True, default=0)

    class Meta:
        db_table = "posthog_datamodelingjob"


def create_queued_data_modeling_job(
    *,
    team_id: int,
    saved_query_id: str,
    workflow_id: str,
    created_by_id: int | None = None,
) -> DataModelingJob:
    existing_job = (
        DataModelingJob.objects.filter(
            team_id=team_id,
            saved_query_id=saved_query_id,
            workflow_id=workflow_id,
            status__in=[DataModelingJob.Status.QUEUED, DataModelingJob.Status.RUNNING],
        )
        .order_by("-created_at")
        .first()
    )
    if existing_job:
        return existing_job

    return DataModelingJob.objects.create(
        team_id=team_id,
        saved_query_id=saved_query_id,
        status=DataModelingJob.Status.QUEUED,
        workflow_id=workflow_id,
        created_by_id=created_by_id,
    )
