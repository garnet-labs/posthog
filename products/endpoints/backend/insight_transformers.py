"""Transform materialized insight endpoint responses from flat HogQL to rich insight format.

When insight queries (TrendsQuery, RetentionQuery, LifecycleQuery) are materialized,
the S3 table stores flat HogQL data. At read time, SELECT * returns flat rows.
This module transforms those flat rows back into the insight-specific response shape
that customers expect (matching what the non-materialized path produces).
"""

from collections import defaultdict
from datetime import datetime
from typing import Any

import structlog

from posthog.schema import HogQLQueryModifiers, HogQLQueryResponse

from posthog.hogql_queries.query_runner import get_query_runner
from posthog.models.team import Team

logger = structlog.get_logger(__name__)


def transform_materialized_insight_response(
    result: dict,
    original_query: dict,
    team: Team,
    now: datetime | None = None,
) -> None:
    """Transform flat HogQL results in-place into insight-specific response shape.

    Args:
        result: The result.data dict from _execute_query_and_respond(). Modified in-place.
        original_query: The original insight query definition (TrendsQuery, etc.)
        team: The team for query runner context.
        now: Pin date range to this timestamp (e.g., saved_query.last_run_at) instead of datetime.now().
    """
    query_kind = original_query.get("kind")

    if query_kind == "TrendsQuery":
        _transform_trends(result, original_query, team, now)
    elif query_kind == "LifecycleQuery":
        _transform_lifecycle(result, original_query, team, now)
    elif query_kind == "RetentionQuery":
        _transform_retention(result, original_query, team, now)


def _make_runner(original_query: dict, team: Team, now: datetime | None = None):
    """Instantiate a query runner from the original query for formatting context."""
    modifiers_dict = original_query.get("modifiers") or {}
    modifiers = HogQLQueryModifiers(**modifiers_dict)
    runner = get_query_runner(
        query=original_query,
        team=team,
        modifiers=modifiers,
    )
    if now is not None:
        # Pin date range to materialization time instead of datetime.now().
        # query_date_range.__init__ only sets private attrs; date_from/date_to/now_with_timezone
        # are lazy @cached_property and haven't been computed yet.
        runner.query_date_range._now_without_timezone = now
    return runner


def _strip_hogql_fields(result: dict) -> None:
    """Remove HogQL-specific fields that don't belong in insight responses."""
    for field in ("columns", "types", "limit", "offset", "query"):
        result.pop(field, None)


def _transform_trends(result: dict, original_query: dict, team: Team, now: datetime | None = None) -> None:
    runner = _make_runner(original_query, team, now)

    columns = result.get("columns", [])
    rows = result.get("results", [])

    if not rows:
        result["results"] = []
        _strip_hogql_fields(result)
        return

    # Group rows by __series_index (trends uses named column access in build_series_response)
    series_index_col = columns.index("__series_index") if "__series_index" in columns else None
    groups: dict[int, list] = defaultdict(list)
    for row in rows:
        idx = row[series_index_col] if series_index_col is not None else 0
        groups[idx].append(row)

    # Build per-series HogQLQueryResponse objects
    per_series_responses: list[HogQLQueryResponse] = []
    for series_idx in sorted(groups.keys()):
        per_series_responses.append(
            HogQLQueryResponse(
                results=groups[series_idx],
                columns=columns,
            )
        )

    # Call build_series_response per series, then format_results for post-processing
    returned_results: list[list[dict[str, Any]]] = []
    series_count = len(per_series_responses)
    for i, response in enumerate(per_series_responses):
        if i < len(runner.series):
            series_with_extra = runner.series[i]
        else:
            logger.warning(
                "Series index mismatch in materialized trends transform",
                series_index=i,
                runner_series_count=len(runner.series),
                team_id=team.id,
            )
            series_with_extra = runner.series[0]
        series_result = runner.build_series_response(response, series_with_extra, series_count)
        if isinstance(series_result, list):
            returned_results.append(series_result)
        elif isinstance(series_result, dict):
            returned_results.append([series_result])

    final_result, has_more = runner.format_results(returned_results)

    result["results"] = final_result
    result["hasMore"] = has_more
    _strip_hogql_fields(result)


def _transform_lifecycle(result: dict, original_query: dict, team: Team, now: datetime | None = None) -> None:
    runner = _make_runner(original_query, team, now)

    columns = result.get("columns", [])
    rows = result.get("results", [])

    if not rows:
        result["results"] = []
        _strip_hogql_fields(result)
        return

    # format_results uses column-name-based access, so column order doesn't matter
    response = HogQLQueryResponse(results=rows, columns=columns)
    result["results"] = runner.format_results(response)
    _strip_hogql_fields(result)


def _transform_retention(result: dict, original_query: dict, team: Team, now: datetime | None = None) -> None:
    runner = _make_runner(original_query, team, now)

    columns = result.get("columns", [])
    rows = result.get("results", [])

    if not rows:
        result["results"] = []
        _strip_hogql_fields(result)
        return

    # format_results uses column-name-based access, so column order doesn't matter
    response = HogQLQueryResponse(results=rows, columns=columns)
    result["results"] = runner.format_results(response)
    _strip_hogql_fields(result)
