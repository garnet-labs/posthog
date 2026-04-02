from dataclasses import dataclass
from typing import Literal

import dagster

from posthog.dags.common import JobOwners, skip_if_already_running
from posthog.dags.common.ops import get_all_team_ids_op
from posthog.dags.common.resources import redis
from posthog.exceptions_capture import capture_exception

from products.growth.backend.sdk_versions import get_and_cache_team_sdk_versions


@dataclass(kw_only=True)
class CacheTeamSdkVersionsResult:
    team_id: int
    sdk_count: int
    status: Literal["success", "empty", "failed", "error"]


@dagster.op(
    retry_policy=dagster.RetryPolicy(
        max_retries=3,
        delay=1,  # 1s
        backoff=dagster.Backoff.EXPONENTIAL,
        jitter=dagster.Jitter.PLUS_MINUS,
    )
)
def cache_team_sdk_versions_for_team_op(
    context: dagster.OpExecutionContext,
    redis_client: dagster.ResourceParam[redis.Redis],
    team_ids: list[int],
) -> list[CacheTeamSdkVersionsResult]:
    """Fetch and cache SDK versions for a batch of teams."""
    results = []

    for team_id in team_ids:
        try:
            sdk_versions = get_and_cache_team_sdk_versions(team_id, redis_client, logger=context.log)

            sdk_count = 0 if sdk_versions is None else len(sdk_versions)

            status: Literal["success", "empty", "failed", "error"] = "error"
            if sdk_versions is not None:
                if len(sdk_versions) == 0:
                    context.log.debug(f"Team {team_id} has no SDK versions")
                    status = "empty"
                else:
                    context.log.info(f"Cached {sdk_count} SDK types for team {team_id}")
                    status = "success"
            else:
                context.log.warning(f"Failed to get SDK versions for team {team_id}")
                status = "failed"

            results.append(CacheTeamSdkVersionsResult(team_id=team_id, sdk_count=sdk_count, status=status))
        except Exception as e:
            context.log.exception(f"Failed to process SDK versions for team {team_id}")
            capture_exception(e)
            results.append(CacheTeamSdkVersionsResult(team_id=team_id, sdk_count=0, status="error"))

    empty_results = [r for r in results if r.status == "empty"]
    failed_results = [r for r in results if r.status in ("failed", "error")]
    success_results = [r for r in results if r.status == "success"]

    context.add_output_metadata(
        {
            "batch_size": dagster.MetadataValue.int(len(team_ids)),
            "processed": dagster.MetadataValue.int(len(results)),
            "empty_count": dagster.MetadataValue.int(len(empty_results)),
            "failed_count": dagster.MetadataValue.int(len(failed_results)),
            "success_count": dagster.MetadataValue.int(len(success_results)),
        }
    )

    return results


@dagster.op
def aggregate_results_op(context: dagster.OpExecutionContext, results: list[list[CacheTeamSdkVersionsResult]]) -> None:
    """Aggregate results from all team processing ops."""
    flat_results = [r for batch in results for r in batch]

    total_teams = len(flat_results)
    cached_count = sum(1 for r in flat_results if r.status == "success")
    empty_count = sum(1 for r in flat_results if r.status == "empty")
    failed_count = sum(1 for r in flat_results if r.status in ("failed", "error"))

    context.log.info(
        f"Completed processing {total_teams} teams: {cached_count} cached, {empty_count} empty, {failed_count} failed"
    )

    context.add_output_metadata(
        {
            "total_teams": dagster.MetadataValue.int(total_teams),
            "cached_count": dagster.MetadataValue.int(cached_count),
            "empty_count": dagster.MetadataValue.int(empty_count),
            "failed_count": dagster.MetadataValue.int(failed_count),
        }
    )

    if failed_count > 0:
        failed_team_ids = [r.team_id for r in flat_results if r.status in ("failed", "error")]
        raise Exception(f"Failed to cache SDK versions for {failed_count} teams: {failed_team_ids}")


@dagster.job(
    description="Queries ClickHouse for recent SDK versions and caches them in Redis",
    # Do this slowly, 5 batches at a time at most, more than this will cause the pod to OOM
    executor_def=dagster.multiprocess_executor.configured({"max_concurrent": 5}),
    tags={"owner": JobOwners.TEAM_GROWTH.value},
)
def cache_all_team_sdk_versions_job():
    team_ids = get_all_team_ids_op()
    results = team_ids.map(cache_team_sdk_versions_for_team_op)
    aggregate_results_op(results.collect())


@dagster.schedule(
    cron_schedule="0 0 * * *",  # Every day at midnight
    job=cache_all_team_sdk_versions_job,
    execution_timezone="UTC",
)
@skip_if_already_running
def cache_all_team_sdk_versions_schedule(context: dagster.ScheduleEvaluationContext):
    return dagster.RunRequest()
