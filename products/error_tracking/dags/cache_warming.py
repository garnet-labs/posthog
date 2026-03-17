from django.utils.dateparse import parse_datetime

import dagster
from dagster import Backoff, Jitter, RetryPolicy
from prometheus_client import Counter, Gauge

from posthog.hogql.constants import LimitContext

from posthog.clickhouse.query_tagging import Feature, tag_queries
from posthog.dags.common import JobOwners
from posthog.dags.common.common import skip_if_already_running
from posthog.dags.common.resources import PostHogAnalyticsResource
from posthog.event_usage import EventSource
from posthog.exceptions_capture import capture_exception
from posthog.hogql_queries.query_cache import DjangoCacheQueryCacheManager
from posthog.hogql_queries.query_runner import get_query_runner
from posthog.models import Team
from posthog.models.instance_setting import get_instance_setting

STALE_ERROR_TRACKING_QUERIES_GAUGE = Gauge(
    "posthog_cache_warming_stale_error_tracking_query_gauge",
    "Number of stale error tracking queries present",
    ["team_id"],
)
ERROR_TRACKING_QUERIES_COUNTER = Counter(
    "posthog_cache_warming_error_tracking_queries",
    "Number of error tracking queries warmed",
    ["team_id", "is_cached"],
)

cache_warming_retry_policy = RetryPolicy(
    max_retries=3,
    delay=2,
    backoff=Backoff.EXPONENTIAL,
    jitter=Jitter.FULL,
)

# The default filterless error tracking listing query, matching what the
# frontend renders when a user first opens the Error tracking page.
DEFAULT_ERROR_TRACKING_QUERY: dict = {
    "kind": "ErrorTrackingQuery",
    "dateRange": {"date_from": "-7d", "date_to": None},
    "orderBy": "last_seen",
    "orderDirection": "DESC",
    "status": "active",
    "limit": 50,
    "volumeResolution": 20,
    "withAggregations": True,
    "withFirstEvent": False,
    "withLastEvent": False,
    "filterTestAccounts": False,
}


def get_teams_enabled_for_error_tracking_cache_warming() -> list[int]:
    return get_instance_setting("ERROR_TRACKING_WARMING_TEAMS_TO_WARM")


def get_queries_for_team(team: Team) -> list[dict]:
    """Return the set of queries to pre-warm for a given team.

    For now this is a single canonical filterless query sorted by last_seen DESC.
    We construct separate variants: one without and one with filterTestAccounts,
    depending on the team setting.
    """
    queries: list[dict] = []

    query = {**DEFAULT_ERROR_TRACKING_QUERY}
    queries.append(query)

    # Also warm the variant with test accounts filtered if the team has that enabled
    if team.test_account_filters:
        query_with_filter = {**DEFAULT_ERROR_TRACKING_QUERY, "filterTestAccounts": True}
        queries.append(query_with_filter)

    return queries


@dagster.op()
def get_teams_for_error_tracking_warming_op(
    context: dagster.OpExecutionContext, posthoganalytics: PostHogAnalyticsResource
) -> list[int]:
    team_ids = get_teams_enabled_for_error_tracking_cache_warming()
    context.log.info(f"Found {len(team_ids)} teams for error tracking cache warming")
    context.add_output_metadata({"team_count": len(team_ids), "team_ids": str(team_ids)})
    return team_ids


@dagster.op
def get_error_tracking_queries_for_teams_op(
    context: dagster.OpExecutionContext,
    team_ids: list[int],
) -> dict:
    all_queries: dict[int, list[dict]] = {}
    query_count = 0

    for team_id in team_ids:
        try:
            team = Team.objects.get(pk=team_id)
        except Team.DoesNotExist:
            context.log.warning(f"Team {team_id} not found, skipping")
            continue

        queries = get_queries_for_team(team)
        context.log.info(f"Prepared {len(queries)} error tracking queries for team {team_id}")
        STALE_ERROR_TRACKING_QUERIES_GAUGE.labels(team_id=team_id).set(len(queries))
        all_queries[team_id] = queries
        query_count += len(queries)

    context.log.info(f"Found {query_count} total error tracking queries to warm")
    context.add_output_metadata({"query_count": query_count, "team_count": len(team_ids)})
    return all_queries


@dagster.op(retry_policy=cache_warming_retry_policy)
def warm_error_tracking_queries_op(context: dagster.OpExecutionContext, queries: dict) -> None:
    queries_warmed = 0
    queries_skipped = 0

    for team_id, query_list in queries.items():
        try:
            team = Team.objects.get(pk=team_id)
        except Team.DoesNotExist:
            context.log.warning(f"Team {team_id} not found, skipping")
            continue

        for query_json in query_list:
            runner = get_query_runner(
                query=query_json,
                team=team,
                limit_context=LimitContext.QUERY_ASYNC,
            )

            cache_manager = DjangoCacheQueryCacheManager(team_id=team.pk, cache_key=runner.get_cache_key())

            try:
                cached_data = cache_manager.get_cache_data()

                if cached_data is not None:
                    last_refresh = parse_datetime(cached_data["last_refresh"])
                    is_stale = runner._is_stale(last_refresh)

                    if not is_stale:
                        context.log.info(f"Error tracking query for team {team_id} already cached, skipping")
                        ERROR_TRACKING_QUERIES_COUNTER.labels(team_id=team_id, is_cached=True).inc()
                        queries_skipped += 1
                        continue

                tag_queries(
                    team_id=team_id,
                    trigger="errorTrackingQueryWarming",
                    feature=Feature.CACHE_WARMUP,
                )

                runner.run(analytics_props={"source": EventSource.CACHE_WARMING})
                ERROR_TRACKING_QUERIES_COUNTER.labels(team_id=team_id, is_cached=False).inc()
                queries_warmed += 1

            except Exception as e:
                context.log.exception(f"Error warming error tracking query for team {team_id}")
                capture_exception(e)

    context.log.info(f"Warmed {queries_warmed} error tracking queries ({queries_skipped} were already cached)")
    context.add_output_metadata({"queries_warmed": queries_warmed, "queries_skipped": queries_skipped})


@dagster.job(
    description="Warms error tracking query cache for the default listing query",
    tags={
        "owner": JobOwners.TEAM_ERROR_TRACKING.value,
        "dagster/error_tracking_cache_warming": "error_tracking_cache_warming",
    },
)
def error_tracking_cache_warming_job():
    team_ids = get_teams_for_error_tracking_warming_op()
    queries = get_error_tracking_queries_for_teams_op(team_ids)
    warm_error_tracking_queries_op(queries)


@dagster.schedule(
    cron_schedule="0 * * * *",
    job=error_tracking_cache_warming_job,
    execution_timezone="UTC",
    tags={"owner": JobOwners.TEAM_ERROR_TRACKING.value},
)
@skip_if_already_running
def error_tracking_cache_warming_schedule(context: dagster.ScheduleEvaluationContext):
    return dagster.RunRequest()
