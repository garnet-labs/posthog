from typing import Any

from posthog.hogql.query import execute_hogql_query

from posthog.models import Team, User
from posthog.sync import database_sync_to_async

from ee.hogai.context.org_intelligence.prompts import (
    METALYTICS_CONTEXT_TEMPLATE,
    METALYTICS_NO_RESULTS,
    METALYTICS_PAGINATION_END,
    METALYTICS_PAGINATION_MORE,
)


class MetalyticsContext:
    def __init__(self, team: Team, user: User):
        self._team = team
        self._user = user

    async def fetch_and_format(
        self,
        *,
        scope: str | None = None,
        date_range: tuple[str, str] | None = None,
        sort_by: str = "views",
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        entries, total = await self._fetch_entries(
            scope=scope,
            date_range=date_range,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )
        return self._format_entries(
            entries,
            total_count=total,
            limit=limit,
            offset=offset,
            scope_filter=scope,
        )

    @database_sync_to_async
    def _fetch_entries(
        self,
        *,
        scope: str | None = None,
        date_range: tuple[str, str] | None = None,
        sort_by: str = "views",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        limit = min(max(limit, 1), 50)

        where_clauses = ["app_source = 'metalytics'"]
        if scope:
            where_clauses.append(f"metric_name = '{scope}'")

        if date_range:
            after_str, before_str = date_range
            where_clauses.append(f"timestamp >= toDateTime64('{after_str}', 6, 'UTC')")
            where_clauses.append(f"timestamp <= toDateTime64('{before_str}', 6, 'UTC')")
        else:
            where_clauses.append("timestamp >= now() - INTERVAL 7 DAY")

        where = " AND ".join(where_clauses)

        order_by = "total_views DESC"
        if sort_by == "unique_users":
            order_by = "unique_viewers DESC"

        query = f"""
            SELECT
                metric_name as resource_type,
                app_source_id as resource_id,
                sum(count) as total_views,
                uniqExact(instance_id) as unique_viewers
            FROM app_metrics2
            WHERE {where}
            GROUP BY resource_type, resource_id
            ORDER BY {order_by}
            LIMIT {limit}
            OFFSET {offset}
        """

        count_query = f"""
            SELECT count(DISTINCT (metric_name, app_source_id)) as cnt
            FROM app_metrics2
            WHERE {where}
        """

        try:
            results = execute_hogql_query(query, team=self._team)
            count_results = execute_hogql_query(count_query, team=self._team)
            total = count_results.results[0][0] if count_results.results else 0

            entries: list[dict[str, Any]] = []
            for row in results.results:
                entries.append(
                    {
                        "resource_type": row[0],
                        "resource_id": row[1],
                        "view_count": row[2],
                        "unique_viewers": row[3],
                    }
                )
            return entries, total
        except Exception:
            return [], 0

    def _format_entries(
        self,
        entries: list[dict[str, Any]],
        *,
        total_count: int,
        limit: int,
        offset: int,
        scope_filter: str | None = None,
    ) -> str:
        if not entries:
            return METALYTICS_NO_RESULTS

        formatted: list[str] = []
        for entry in entries:
            formatted.append(
                f"- {entry['resource_type']} #{entry['resource_id']} | "
                f"{entry['view_count']} views | {entry['unique_viewers']} unique viewers"
            )

        filter_desc = f" for {scope_filter}" if scope_filter else ""
        has_more = total_count > offset + limit
        pagination_hint = (
            METALYTICS_PAGINATION_MORE.format(next_offset=offset + limit) if has_more else METALYTICS_PAGINATION_END
        )

        return METALYTICS_CONTEXT_TEMPLATE.format(
            count=len(entries),
            scope_filter=filter_desc,
            date_range_desc="last 7 days",
            entries="\n".join(formatted),
            pagination_hint=pagination_hint,
        )
