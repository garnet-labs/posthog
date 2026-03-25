from typing import TYPE_CHECKING, Any, Optional

import orjson
import structlog
import posthoganalytics
from redis.exceptions import RedisError
from rest_framework import status
from rest_framework.response import Response

from posthog import settings
from posthog.api.query_coalescer import CoalesceSignal, QueryCoalescer
from posthog.hogql_queries.query_runner import ExecutionMode

if TYPE_CHECKING:
    from rest_framework.request import Request

    from posthog.models import Team

logger = structlog.get_logger(__name__)


class QueryCoalescingMixin:
    """Mixin that provides HTTP-level query coalescing for viewsets.

    Deduplicates concurrent identical queries by letting one request (leader)
    execute while others (followers) wait for the result. Requires the viewset
    to provide ``self.team`` (e.g. via ``TeamAndOrgViewSetMixin``).
    """

    team: "Team"
    _coalescer: Optional[QueryCoalescer]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._coalescer = None

    def _try_coalesce(
        self, coalescing_key: str, execution_mode: ExecutionMode, client_query_id: str | None
    ) -> tuple[Optional[Response], ExecutionMode]:
        """Attempt query coalescing.

        Returns a (response, execution_mode) tuple.  The response is non-None only
        when a follower must short-circuit (e.g. replay an error or report a timeout).
        The returned execution_mode may differ from the input: force_blocking followers
        are downgraded to blocking so they hit the cache populated by the leader.
        """
        # Coalescing applies to both regular blocking queries and force_blocking queries.
        # force_blocking followers are downgraded to RECENT_CACHE_CALCULATE_BLOCKING_IF_STALE
        # on DONE so they read from the cache the leader just populated, rather than recalculating.
        if execution_mode not in (
            ExecutionMode.RECENT_CACHE_CALCULATE_BLOCKING_IF_STALE,
            ExecutionMode.CALCULATE_BLOCKING_ALWAYS,
        ):
            return None, execution_mode

        enabled = posthoganalytics.feature_enabled(
            "http-query-coalescing",
            str(self.team.pk),
        )

        coalescer = QueryCoalescer(coalescing_key, dry_run=not enabled)

        log = logger.bind(coalescing_key=coalescing_key, query_id=client_query_id)

        # Dry run: all requests still compete for the lock so we can measure how many
        # concurrent duplicates exist (follower_dry_run metric). Leaders proceed normally
        # (the Redis overhead is minimal). Followers return immediately without waiting.
        try:
            is_leader = coalescer.try_acquire()
        except RedisError:
            log.warning("query_coalescing_redis_error", msg="redis unavailable, skipping coalescing")
            return None, execution_mode

        if is_leader:
            log.info("query_coalescing_leader_start")
            self._coalescer = coalescer
            return None, execution_mode

        if not enabled:
            return None, execution_mode

        # Follower path
        log.info("query_coalescing_follower_waiting")

        signal = coalescer.wait_for_signal(max_wait=settings.QUERY_COALESCING_MAX_WAIT_SECONDS)

        if signal == CoalesceSignal.DONE:
            log.info("query_coalescing_follower_done")
            # Followers fall through to cache-aware mode so they read the result
            # the leader just wrote, instead of recalculating.
            return None, ExecutionMode.RECENT_CACHE_CALCULATE_BLOCKING_IF_STALE

        if signal == CoalesceSignal.ERROR:
            error_data = coalescer.get_error_response()
            if error_data:
                log.info("query_coalescing_follower_replaying_error", status=error_data["status"])
                try:
                    body = orjson.loads(error_data["body"])
                except Exception:
                    log.warning("query_coalescing_follower_body_parse_failed")
                    return None, execution_mode
                return Response(
                    data=body,
                    status=error_data["status"],
                ), execution_mode
            # Couldn't read error, fall through
            log.warning("query_coalescing_follower_error_read_failed")
            return None, execution_mode

        if signal == CoalesceSignal.TIMEOUT:
            log.warning("query_coalescing_follower_timeout")
            return Response(
                data={"type": "server_error", "detail": "Query is still running, please try again shortly."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ), execution_mode

        log.info("query_coalescing_follower_fallthrough", signal=signal)
        return None, execution_mode

    def finalize_response(self, request: "Request", response: Response, *args: Any, **kwargs: Any) -> Response:
        try:
            response = super().finalize_response(request, response, *args, **kwargs)
        finally:
            if self._coalescer and self._coalescer.is_leader:
                try:
                    if response.status_code >= 400:
                        response.render()
                        self._coalescer.store_error_response(response.status_code, response.content)
                    else:
                        self._coalescer.mark_done()
                except Exception:
                    logger.warning("query_coalescing_finalize_error", exc_info=True)
                finally:
                    self._coalescer.cleanup()

        return response
