from datetime import timedelta

from django.db.models import Count, Max
from django.utils import timezone

from posthog.batch_exports.models import BatchExportRun
from posthog.dags.common.owners import JobOwners
from posthog.models.health_issue import HealthIssue
from posthog.temporal.health_checks.detectors import DEFAULT_EXECUTION_POLICY
from posthog.temporal.health_checks.framework import HealthCheck
from posthog.temporal.health_checks.models import HealthCheckResult

BATCH_EXPORT_LOOKBACK_DAYS = 3
BATCH_EXPORT_MIN_FAILURES = 3

FAILURE_STATUSES = [
    BatchExportRun.Status.FAILED,
    BatchExportRun.Status.FAILED_RETRYABLE,
    BatchExportRun.Status.FAILED_BILLING,
    BatchExportRun.Status.TIMEDOUT,
    BatchExportRun.Status.TERMINATED,
]


class BatchExportFailureCheck(HealthCheck):
    name = "batch_export_failure"
    kind = "batch_export_failure"
    owner = JobOwners.TEAM_DATA_STACK
    policy = DEFAULT_EXECUTION_POLICY

    def detect(self, team_ids: list[int]) -> dict[int, list[HealthCheckResult]]:
        cutoff = timezone.now() - timedelta(days=BATCH_EXPORT_LOOKBACK_DAYS)

        rows = (
            BatchExportRun.objects.filter(
                batch_export__team_id__in=team_ids,
                batch_export__deleted=False,
                batch_export__paused=False,
                status__in=FAILURE_STATUSES,
                created_at__gte=cutoff,
            )
            .values("batch_export__team_id", "batch_export_id", "batch_export__name")
            .annotate(failure_count=Count("id"), last_failure_at=Max("created_at"))
            .filter(failure_count__gte=BATCH_EXPORT_MIN_FAILURES)
        )

        issues: dict[int, list[HealthCheckResult]] = {}
        for row in rows:
            team_id = row["batch_export__team_id"]
            issues.setdefault(team_id, []).append(
                HealthCheckResult(
                    severity=HealthIssue.Severity.WARNING,
                    payload={
                        "pipeline_type": "batch_export",
                        "pipeline_id": str(row["batch_export_id"]),
                        "pipeline_name": row["batch_export__name"],
                        "failure_count": row["failure_count"],
                        "last_failure_at": row["last_failure_at"].isoformat(),
                    },
                    hash_keys=["pipeline_type", "pipeline_id"],
                )
            )

        return issues
