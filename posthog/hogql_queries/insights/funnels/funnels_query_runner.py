from datetime import datetime, timedelta
from math import ceil
from typing import Any, Optional

import structlog

from posthog.schema import (
    BreakdownType,
    CachedFunnelsQueryResponse,
    CohortPropertyFilter,
    FilterLogicalOperator,
    FunnelsQuery,
    FunnelsQueryResponse,
    FunnelVizType,
    HogQLQueryModifiers,
    PropertyGroupFilter,
    PropertyGroupFilterValue,
    PropertyOperator,
    ResolvedDateRangeResponse,
)

from posthog.hogql import ast
from posthog.hogql.constants import MAX_BYTES_BEFORE_EXTERNAL_GROUP_BY, HogQLGlobalSettings, LimitContext
from posthog.hogql.printer import to_printed_hogql
from posthog.hogql.query import execute_hogql_query
from posthog.hogql.timings import HogQLTimings

from posthog.caching.insights_api import BASE_MINIMUM_INSIGHT_REFRESH_INTERVAL, REDUCED_MINIMUM_INSIGHT_REFRESH_INTERVAL
from posthog.hogql_queries.insights.funnels import FunnelTrendsUDF, FunnelUDF
from posthog.hogql_queries.insights.funnels.funnel_query_context import FunnelQueryContext
from posthog.hogql_queries.insights.funnels.funnel_time_to_convert import FunnelTimeToConvertUDF
from posthog.hogql_queries.query_runner import AnalyticsQueryRunner
from posthog.hogql_queries.utils.query_date_range import QueryDateRange
from posthog.models import Team
from posthog.models.cohort import Cohort
from posthog.models.filters.mixins.utils import cached_property
from posthog.queries.breakdown_props import NOT_IN_COHORT_ID

logger = structlog.get_logger(__name__)


class FunnelsQueryRunner(AnalyticsQueryRunner[FunnelsQueryResponse]):
    query: FunnelsQuery
    cached_response: CachedFunnelsQueryResponse
    context: FunnelQueryContext

    def __init__(
        self,
        query: FunnelsQuery | dict[str, Any],
        team: Team,
        timings: Optional[HogQLTimings] = None,
        modifiers: Optional[HogQLQueryModifiers] = None,
        limit_context: Optional[LimitContext] = None,
        just_summarize: bool = False,
    ):
        super().__init__(query, team=team, timings=timings, modifiers=modifiers, limit_context=limit_context)

        self.just_summarize = just_summarize
        self.context = FunnelQueryContext(
            query=self.query, team=team, timings=timings, modifiers=modifiers, limit_context=limit_context
        )

    def _refresh_frequency(self):
        date_to = self.query_date_range.date_to()
        date_from = self.query_date_range.date_from()
        interval = self.query_date_range.interval_name

        delta_days: Optional[int] = None
        if date_from and date_to:
            delta = date_to - date_from
            delta_days = ceil(delta.total_seconds() / timedelta(days=1).total_seconds())

        refresh_frequency = BASE_MINIMUM_INSIGHT_REFRESH_INTERVAL
        if interval == "hour" or (delta_days is not None and delta_days <= 7):
            # The interval is shorter for short-term insights
            refresh_frequency = REDUCED_MINIMUM_INSIGHT_REFRESH_INTERVAL

        return refresh_frequency

    def to_query(self) -> ast.SelectQuery:
        return self.funnel_class.get_query()

    def to_actors_query(self) -> ast.SelectQuery:
        return self.funnel_actor_class.actor_query()

    @cached_property
    def _single_cohort_id(self) -> int | None:
        """Returns the cohort ID if this is a single-cohort breakdown, else None."""
        bf = self.query.breakdownFilter
        if not bf or bf.breakdown_type != BreakdownType.COHORT:
            return None
        breakdown = bf.breakdown
        if isinstance(breakdown, list) and len(breakdown) == 1 and breakdown[0] != "all":
            try:
                return int(breakdown[0])
            except (ValueError, TypeError):
                return None
        if isinstance(breakdown, int):
            return breakdown
        return None

    def _calculate(self):
        funnel_viz_type = self.context.funnelsFilter.funnelVizType
        if self._single_cohort_id is not None and funnel_viz_type != FunnelVizType.TIME_TO_CONVERT:
            return self._calculate_single_cohort_breakdown()

        return self._calculate_single_query()

    def _calculate_single_query(self):
        query = self.to_query()
        timings = []

        # TODO: can we get this from execute_hogql_query as well?
        hogql = to_printed_hogql(query, self.team)

        response = execute_hogql_query(
            query_type="FunnelsQuery",
            query=query,
            team=self.team,
            timings=self.timings,
            modifiers=self.modifiers,
            limit_context=self.limit_context,
            settings=HogQLGlobalSettings(
                # Make sure funnel queries never OOM
                max_bytes_before_external_group_by=MAX_BYTES_BEFORE_EXTERNAL_GROUP_BY,
                allow_experimental_analyzer=True,
            ),
        )

        results = self.funnel_class._format_results(response.results)

        if response.timings is not None:
            timings.extend(response.timings)

        return FunnelsQueryResponse(
            results=results,
            timings=timings,
            hogql=hogql,
            modifiers=self.modifiers,
            resolved_date_range=ResolvedDateRangeResponse(
                date_from=self.query_date_range.date_from(),
                date_to=self.query_date_range.date_to(),
            ),
        )

    def _create_cohort_sub_query(self, cohort_id: int, negate: bool) -> FunnelsQuery:
        """Create a copy of the query filtered to cohort members (or non-members), with breakdown removed."""
        sub_query = self.query.model_copy(deep=True)
        sub_query.breakdownFilter = None

        cohort_filter = CohortPropertyFilter(
            key="id",
            value=cohort_id,
            operator=PropertyOperator.NOT_IN if negate else PropertyOperator.IN_,
        )

        existing_props = sub_query.properties or []
        if isinstance(existing_props, list):
            sub_query.properties = [*existing_props, cohort_filter]
        else:
            # PropertyGroupFilter — preserve existing group semantics (e.g. OR) as a nested value
            sub_query.properties = PropertyGroupFilter(
                type=FilterLogicalOperator.AND_,
                values=[
                    PropertyGroupFilterValue(
                        type=existing_props.type,
                        values=existing_props.values,
                    ),
                    PropertyGroupFilterValue(
                        type=FilterLogicalOperator.AND_,
                        values=[cohort_filter],
                    ),
                ],
            )

        return sub_query

    def _run_sub_query(self, sub_query: FunnelsQuery) -> FunnelsQueryResponse:
        runner = FunnelsQueryRunner(
            query=sub_query,
            team=self.team,
            timings=self.timings,
            modifiers=self.modifiers,
            limit_context=self.limit_context,
            just_summarize=self.just_summarize,
        )
        return runner._calculate_single_query()

    def _calculate_single_cohort_breakdown(self) -> FunnelsQueryResponse:
        cohort_id = self._single_cohort_id
        assert cohort_id is not None

        try:
            cohort = Cohort.objects.get(pk=cohort_id, team__project_id=self.team.project_id)
            cohort_name = cohort.name or str(cohort_id)
        except Cohort.DoesNotExist:
            cohort_name = str(cohort_id)

        logger.info(
            "funnel_single_cohort_split",
            cohort_id=cohort_id,
            cohort_name=cohort_name,
            team_id=self.team.pk,
        )

        in_query = self._create_cohort_sub_query(cohort_id, negate=False)
        not_in_query = self._create_cohort_sub_query(cohort_id, negate=True)

        in_response = self._run_sub_query(in_query)
        not_in_response = self._run_sub_query(not_in_query)

        timings = [*(in_response.timings or []), *(not_in_response.timings or [])]
        hogql = in_response.hogql or ""

        funnel_viz_type = self.context.funnelsFilter.funnelVizType

        results: list[dict[str, Any]] | list[list[dict[str, Any]]]
        if funnel_viz_type == FunnelVizType.TRENDS:
            results = self._merge_trends_results(in_response.results, not_in_response.results, cohort_id, cohort_name)
        else:
            results = self._merge_steps_results(in_response.results, not_in_response.results, cohort_id, cohort_name)

        return FunnelsQueryResponse(
            results=results,
            timings=timings,
            hogql=hogql,
            modifiers=self.modifiers,
            resolved_date_range=ResolvedDateRangeResponse(
                date_from=self.query_date_range.date_from(),
                date_to=self.query_date_range.date_to(),
            ),
        )

    def _empty_steps(self) -> list[dict[str, Any]]:
        """Generate zero-count step dicts for when a sub-query returns no results."""
        steps = []
        for index, step in enumerate(self.query.series):
            serialized = self.funnel_class._serialize_step(step, 0, index, [])
            serialized.update({"average_conversion_time": None, "median_conversion_time": None})
            steps.append(serialized)
        return steps

    def _merge_steps_results(
        self,
        in_results: list,
        not_in_results: list,
        cohort_id: int,
        cohort_name: str,
    ) -> list[list[dict[str, Any]]]:
        # Without a breakdown, _format_results returns a flat list of step dicts.
        # With a breakdown, the frontend expects a list of lists (one per breakdown value).
        in_steps = in_results if isinstance(in_results, list) and in_results else self._empty_steps()
        not_in_steps = not_in_results if isinstance(not_in_results, list) and not_in_results else self._empty_steps()

        for step in in_steps:
            step["breakdown"] = cohort_name
            step["breakdown_value"] = cohort_id

        not_in_label = f"Not in {cohort_name}"
        for step in not_in_steps:
            step["breakdown"] = not_in_label
            step["breakdown_value"] = NOT_IN_COHORT_ID

        return [in_steps, not_in_steps]

    def _merge_trends_results(
        self,
        in_results: list,
        not_in_results: list,
        cohort_id: int,
        cohort_name: str,
    ) -> list[dict[str, Any]]:
        # Trends _format_results returns a list of dicts, each with optional breakdown_value.
        # For single-cohort split, each sub-query returns one group (no breakdown_value key).
        not_in_label = f"Not in {cohort_name}"

        for entry in in_results:
            entry["breakdown_value"] = cohort_name

        for entry in not_in_results:
            entry["breakdown_value"] = not_in_label

        return [*in_results, *not_in_results]

    @cached_property
    def funnel_order_class(self):
        return FunnelUDF(context=self.context)

    @cached_property
    def funnel_class(self):
        funnelVizType = self.context.funnelsFilter.funnelVizType

        if funnelVizType == FunnelVizType.TRENDS:
            return FunnelTrendsUDF(context=self.context, just_summarize=self.just_summarize)
        elif funnelVizType == FunnelVizType.TIME_TO_CONVERT:
            return FunnelTimeToConvertUDF(context=self.context)
        else:
            return self.funnel_order_class

    @cached_property
    def funnel_actor_class(self):
        if self.context.funnelsFilter.funnelVizType == FunnelVizType.TRENDS:
            return FunnelTrendsUDF(context=self.context)

        return FunnelUDF(context=self.context)

    @property
    def exact_timerange(self):
        return self.query.dateRange and self.query.dateRange.explicitDate

    @cached_property
    def query_date_range(self):
        return QueryDateRange(
            date_range=self.query.dateRange,
            team=self.team,
            interval=self.query.interval,
            now=datetime.now(),
            exact_timerange=self.exact_timerange,
        )
