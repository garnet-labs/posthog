from django.utils.dateparse import parse_datetime

import structlog
from celery import shared_task
from prometheus_client import Counter, Gauge

from posthog.hogql.constants import LimitContext

from posthog.clickhouse.query_tagging import Feature, tag_queries
from posthog.event_usage import EventSource
from posthog.exceptions_capture import capture_exception
from posthog.hogql_queries.query_cache import DjangoCacheQueryCacheManager
from posthog.hogql_queries.query_runner import get_query_runner
from posthog.models import Team
from posthog.models.instance_setting import get_instance_setting
from posthog.tasks.utils import CeleryQueue

logger = structlog.get_logger(__name__)

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


@shared_task(ignore_result=True, expires=60 * 15)
def schedule_error_tracking_cache_warming_task() -> None:
    """Scheduler task that fans out per-team warming tasks via Celery."""
    team_ids = get_teams_enabled_for_error_tracking_cache_warming()
    logger.info("error_tracking_cache_warming_scheduled", team_count=len(team_ids), team_ids=team_ids)

    for team_id in team_ids:
        warm_error_tracking_cache_for_team_task.delay(team_id)


@shared_task(
    queue=CeleryQueue.ANALYTICS_LIMITED.value,
    ignore_result=True,
    expires=60 * 60,
    autoretry_for=(Exception,),
    retry_backoff=2,
    retry_backoff_max=30,
    max_retries=3,
)
def warm_error_tracking_cache_for_team_task(team_id: int) -> None:
    """Warm error tracking cache for a single team."""
    try:
        team = Team.objects.get(pk=team_id)
    except Team.DoesNotExist:
        logger.warning("error_tracking_cache_warming_team_not_found", team_id=team_id)
        return

    queries = get_queries_for_team(team)
    STALE_ERROR_TRACKING_QUERIES_GAUGE.labels(team_id=team_id).set(len(queries))

    queries_warmed = 0
    queries_skipped = 0

    for query_json in queries:
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
                    logger.info("error_tracking_query_already_cached", team_id=team_id)
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
            logger.exception("error_tracking_cache_warming_query_failed", team_id=team_id)
            capture_exception(e)

    logger.info(
        "error_tracking_cache_warming_complete",
        team_id=team_id,
        queries_warmed=queries_warmed,
        queries_skipped=queries_skipped,
    )
