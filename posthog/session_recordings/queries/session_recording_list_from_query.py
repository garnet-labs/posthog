from datetime import UTC, datetime, timedelta
from typing import Any, Literal, NamedTuple, Union, cast

import structlog
import posthoganalytics
from opentelemetry import trace

from posthog.schema import (
    FilterLogicalOperator,
    HogQLQueryModifiers,
    PropertyGroupFilterValue,
    PropertyOperator,
    RecordingOrder,
    RecordingPropertyFilter,
    RecordingsQuery,
)

from posthog.hogql import ast
from posthog.hogql.constants import HogQLGlobalSettings
from posthog.hogql.database.schema.util.uuid import uuid_uint128_to_uuid_expr
from posthog.hogql.parser import parse_select
from posthog.hogql.property import property_to_expr

from posthog.exceptions_capture import capture_exception
from posthog.hogql_queries.insights.paginators import HogQLCursorPaginator, HogQLHasMorePaginator
from posthog.models import Team
from posthog.session_recordings.queries.sub_queries.base_query import SessionRecordingsListingBaseQuery
from posthog.session_recordings.queries.sub_queries.cohort_subquery import CohortPropertyGroupsSubQuery
from posthog.session_recordings.queries.sub_queries.events_subquery import ReplayFiltersEventsSubQuery
from posthog.session_recordings.queries.sub_queries.person_ids_subquery import PersonsIdCompareOperation
from posthog.session_recordings.queries.sub_queries.person_props_subquery import PersonsPropertiesSubQuery
from posthog.session_recordings.queries.utils import (
    SessionRecordingQueryResult,
    UnexpectedQueryProperties,
    _strip_person_and_event_and_cohort_properties,
    expand_test_account_filters,
)
from posthog.types import AnyPropertyFilter

# Mapping from property filter key to sessions v3 array column name
SESSIONS_V3_PROPERTY_COLUMN_MAP: dict[str, dict[str, str]] = {
    # event properties
    "event": {
        "$host": "hosts",
        "$current_url": "urls",
    },
    # person properties
    "person": {
        "email": "emails",
    },
}


SESSIONS_V3_SUPPORTED_OPERATORS: frozenset[PropertyOperator] = frozenset(
    {
        PropertyOperator.EXACT,
        PropertyOperator.IS_NOT,
        PropertyOperator.ICONTAINS,
        PropertyOperator.NOT_ICONTAINS,
        PropertyOperator.REGEX,
        PropertyOperator.NOT_REGEX,
        PropertyOperator.IS_SET,
        PropertyOperator.IS_NOT_SET,
    }
)


class SessionsV3PropertyFilter(NamedTuple):
    column: str
    operator: PropertyOperator
    value: Any


logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


def _is_sessions_v3_enabled(team_id: int) -> bool:
    return posthoganalytics.feature_enabled(
        "replay-filters-via-sessions-v3",
        str(team_id),
        send_feature_flag_events=False,
    )


class SessionRecordingListFromQuery(SessionRecordingsListingBaseQuery):
    SESSION_RECORDINGS_DEFAULT_LIMIT = 50

    _team: Team
    _query: RecordingsQuery

    BASE_QUERY: str = """
        SELECT s.session_id,
            any(s.team_id),
            any(s.distinct_id),
            min(s.min_first_timestamp) as start_time,
            max(s.max_last_timestamp) as end_time,
            dateDiff('SECOND', start_time, end_time) as duration,
            argMinMerge(s.first_url) as first_url,
            sum(s.click_count) as click_count,
            sum(s.keypress_count) as keypress_count,
            sum(s.mouse_activity_count) as mouse_activity_count,
            sum(s.active_milliseconds)/1000 as active_seconds,
            (duration - active_seconds) as inactive_seconds,
            sum(s.console_log_count) as console_log_count,
            sum(s.console_warn_count) as console_warn_count,
            sum(s.console_error_count) as console_error_count,
            max(s.retention_period_days) as retention_period_days,
            dateTrunc('DAY', start_time) + toIntervalDay(coalesce(retention_period_days, 30)) as expiry_time,
            date_diff('DAY', {python_now}, expiry_time) as recording_ttl,
            {ongoing_selection},
            round((
            ((sum(s.active_milliseconds) / 1000 + sum(s.click_count) + sum(s.keypress_count) + sum(s.console_error_count))) -- intent
            /
            ((sum(s.mouse_activity_count) + dateDiff('SECOND', start_time, end_time) + sum(s.console_error_count) + sum(s.console_log_count) + sum(s.console_warn_count)))
            * 100
            ), 2) as activity_score
        FROM raw_session_replay_events s
        WHERE {where_predicates}
        GROUP BY session_id
        HAVING {having_predicates}
        """

    @staticmethod
    def _get_result_columns() -> list[str]:
        """Returns the column order of the query results"""
        return [
            "session_id",
            "team_id",
            "distinct_id",
            "start_time",
            "end_time",
            "duration",
            "first_url",
            "click_count",
            "keypress_count",
            "mouse_activity_count",
            "active_seconds",
            "inactive_seconds",
            "console_log_count",
            "console_warn_count",
            "console_error_count",
            "retention_period_days",
            "expiry_time",
            "recording_ttl",
            "ongoing",
            "activity_score",
        ]

    @staticmethod
    def _data_to_return(results: list[Any] | None) -> list[dict[str, Any]]:
        default_columns = SessionRecordingListFromQuery._get_result_columns()

        return [
            {
                **dict(zip(default_columns, row[: len(default_columns)])),
            }
            for row in results or []
        ]

    def __init__(
        self,
        team: Team,
        query: RecordingsQuery,
        hogql_query_modifiers: HogQLQueryModifiers | None = None,
        allow_event_property_expansion: bool = False,
        max_execution_time: int | None = None,
        **_,
    ):
        # TRICKY: we need to make sure we init test account filters only once,
        # otherwise we'll end up with a lot of duplicated test account filters in the query
        expanded_query = query.model_copy(deep=True)
        if expanded_query.filter_test_accounts:
            expanded_query.properties = expand_test_account_filters(team) + (expanded_query.properties or [])

        # Convert $lib event property filters to snapshot_library recording filters
        # This avoids expensive events table scans by using the pre-aggregated column
        if expanded_query.properties:
            remaining_properties = []
            for prop in expanded_query.properties:
                if getattr(prop, "type", None) == "event" and getattr(prop, "key", None) == "$lib":
                    # Convert to recording property filter and add to having_predicates
                    recording_filter = RecordingPropertyFilter(
                        type="recording",
                        key="snapshot_library",
                        value=getattr(prop, "value", None),
                        operator=getattr(prop, "operator", PropertyOperator.EXACT),
                    )
                    expanded_query.having_predicates = (expanded_query.having_predicates or []) + [recording_filter]
                else:
                    remaining_properties.append(prop)
            expanded_query.properties = remaining_properties if remaining_properties else None

        # Intercept eligible property filters to route through sessions v3 instead of
        # the events table. This avoids expensive events table scans for common filters
        # like $host, $current_url (event properties) and email (person property).
        #
        # Note: the sessions v3 `emails` column contains all emails seen across events in
        # the session, whereas the existing PersonsPropertiesSubQuery checks the *current*
        # person record. For test-account filtering (email not_icontains @company.com) this
        # is equivalent or better — it catches sessions even if the person was updated since.
        self._sessions_v3_property_filters: list[SessionsV3PropertyFilter] = []
        self._sessions_v3_event_names: list[str] = []
        self._use_sessions_v3 = _is_sessions_v3_enabled(team.id)

        if self._use_sessions_v3 and expanded_query.properties:
            remaining_properties_v3: list[AnyPropertyFilter] = []
            for prop in expanded_query.properties:
                prop_type = getattr(prop, "type", None)
                prop_key = getattr(prop, "key", None)
                column_map = SESSIONS_V3_PROPERTY_COLUMN_MAP.get(prop_type or "", {})
                column = column_map.get(prop_key or "")
                operator = getattr(prop, "operator", None) or PropertyOperator.EXACT
                if column and operator in SESSIONS_V3_SUPPORTED_OPERATORS:
                    self._sessions_v3_property_filters.append(
                        SessionsV3PropertyFilter(
                            column=column,
                            operator=operator,
                            value=getattr(prop, "value", None),
                        )
                    )
                else:
                    remaining_properties_v3.append(prop)
            expanded_query.properties = remaining_properties_v3 if remaining_properties_v3 else None

        # Intercept simple event entities (no property filters) to route through
        # sessions v3 event_names column instead of scanning the events table
        if self._use_sessions_v3 and expanded_query.events:
            remaining_events: list[dict[str, Any]] = []
            for event_dict in expanded_query.events:
                event_name = event_dict.get("id") or event_dict.get("name")
                has_properties = bool(event_dict.get("properties"))
                if event_name and not has_properties:
                    self._sessions_v3_event_names.append(str(event_name))
                else:
                    remaining_events.append(event_dict)
            expanded_query.events = remaining_events if remaining_events else None

        super().__init__(team, expanded_query)

        # Use offset-based pagination only when offset is explicitly provided, otherwise use cursor-based
        # This provides backward compatibility while making cursor-based the default
        if expanded_query.offset is not None:
            # Backward compatibility: use offset-based pagination when offset is explicitly provided
            self._paginator: Union[HogQLCursorPaginator, HogQLHasMorePaginator] = HogQLHasMorePaginator(
                limit=expanded_query.limit or self.SESSION_RECORDINGS_DEFAULT_LIMIT, offset=expanded_query.offset
            )
        else:
            # Default: use cursor-based pagination (even on first page without 'after')
            order_field = expanded_query.order.value if expanded_query.order else RecordingOrder.START_TIME
            order_direction = expanded_query.order_direction or "DESC"

            # Create field index mapping for cursor extraction from tuple results
            field_indices = {field: idx for idx, field in enumerate(self._get_result_columns())}

            self._paginator = HogQLCursorPaginator(
                limit=expanded_query.limit or self.SESSION_RECORDINGS_DEFAULT_LIMIT,
                after=expanded_query.after,
                order_field=order_field,
                order_direction=order_direction,
                secondary_sort_field="session_id",
                field_indices=field_indices,
                use_having_clause=True,  # Session recordings query uses GROUP BY, so cursor conditions must be in HAVING
            )
        self._hogql_query_modifiers = hogql_query_modifiers
        self._allow_event_property_expansion = allow_event_property_expansion
        self._max_execution_time = max_execution_time

    @tracer.start_as_current_span("SessionRecordingListFromQuery.run")
    def run(self) -> SessionRecordingQueryResult:
        query = self.get_query()

        with tracer.start_as_current_span("SessionRecordingListFromQuery.paginate"):
            paginated_response = self._paginator.execute_hogql_query(
                # TODO I guess the paginator needs to know how to handle union queries or all callers are supposed to collapse them or .... 🤷
                query=cast(ast.SelectQuery, query),
                team=self._team,
                query_type="SessionRecordingListQuery",
                modifiers=self._hogql_query_modifiers,
                settings=HogQLGlobalSettings(
                    enable_analyzer=None,
                    **(
                        {"max_execution_time": self._max_execution_time} if self._max_execution_time is not None else {}
                    ),
                ),
            )

        with tracer.start_as_current_span("SessionRecordingListFromQuery._data_to_return"):
            next_cursor = None
            if isinstance(self._paginator, HogQLCursorPaginator):
                next_cursor = self._paginator.get_next_cursor()

            return SessionRecordingQueryResult(
                results=(self._data_to_return(self._paginator.results)),
                has_more_recording=self._paginator.has_more(),
                timings=paginated_response.timings,
                next_cursor=next_cursor,
            )

    @tracer.start_as_current_span("SessionRecordingListFromQuery.get_query")
    def get_query(self):
        parsed_query = parse_select(
            self.BASE_QUERY,
            {
                # Check if the most recent _timestamp is within five minutes of the current time
                # proxy for a live session
                "ongoing_selection": ast.Alias(
                    alias="ongoing",
                    expr=ast.CompareOperation(
                        left=ast.Call(name="max", args=[ast.Field(chain=["s", "_timestamp"])]),
                        right=ast.Constant(
                            # provided in a placeholder, so we can pass now from python to make tests easier 🙈
                            value=datetime.now(UTC) - timedelta(minutes=5),
                        ),
                        op=ast.CompareOperationOp.GtEq,
                    ),
                ),
                "where_predicates": self._where_predicates(),
                "having_predicates": self._having_predicates() or ast.Constant(value=True),
                "python_now": ast.Constant(value=datetime.now(UTC)),
            },
        )
        if isinstance(parsed_query, ast.SelectSetQuery):
            raise Exception("replay does not support SelectSetQuery")

        # Include session_id as a tie-breaker for stable cursor-based pagination
        parsed_query.order_by = [
            self._order_by_clause(),
            ast.OrderExpr(
                expr=ast.Field(chain=["session_id"]),
                order=cast(Literal["ASC", "DESC"], self._query.order_direction or "DESC"),
            ),
        ]
        return parsed_query

    @tracer.start_as_current_span("SessionRecordingListFromQuery._order_by_clause")
    def _order_by_clause(self) -> ast.OrderExpr:
        # KLUDGE: we only need a default here because mypy is silly
        order_by = self._query.order.value if self._query.order else RecordingOrder.START_TIME
        direction = cast(Literal["ASC", "DESC"], self._query.order_direction or "DESC")

        return ast.OrderExpr(expr=ast.Field(chain=[order_by]), order=direction)

    def _property_filter_to_array_expr(
        self, f: SessionsV3PropertyFilter, col_override: ast.Expr | None = None
    ) -> ast.Expr:
        """Translate a property filter into an array predicate on a sessions v3 column."""
        table = "raw_sessions_v3"
        col: ast.Expr = col_override if col_override is not None else ast.Field(chain=[table, f.column])
        val = f.value

        # Unwrap single-element lists for operators that expect scalar values
        scalar_val = val[0] if isinstance(val, list) and len(val) == 1 else val

        match f.operator:
            case PropertyOperator.EXACT:
                if isinstance(val, list):
                    return ast.Call(name="hasAny", args=[col, ast.Constant(value=val)])
                return ast.Call(name="has", args=[col, ast.Constant(value=val)])
            case PropertyOperator.IS_NOT:
                if isinstance(val, list):
                    return ast.Not(expr=ast.Call(name="hasAny", args=[col, ast.Constant(value=val)]))
                return ast.Not(expr=ast.Call(name="has", args=[col, ast.Constant(value=val)]))
            case PropertyOperator.ICONTAINS:
                if isinstance(scalar_val, list):
                    # Multi-value: any element in array matches any search term
                    return ast.Call(
                        name="arrayExists",
                        args=[
                            ast.Lambda(
                                args=["x"],
                                expr=ast.Call(
                                    name="multiSearchAnyCaseInsensitive",
                                    args=[ast.Field(chain=["x"]), ast.Constant(value=scalar_val)],
                                ),
                            ),
                            col,
                        ],
                    )
                return ast.Call(
                    name="arrayExists",
                    args=[
                        ast.Lambda(
                            args=["x"],
                            expr=ast.Call(
                                name="ilike",
                                args=[ast.Field(chain=["x"]), ast.Constant(value=f"%{scalar_val}%")],
                            ),
                        ),
                        col,
                    ],
                )
            case PropertyOperator.NOT_ICONTAINS:
                if isinstance(scalar_val, list):
                    return ast.Not(
                        expr=ast.Call(
                            name="arrayExists",
                            args=[
                                ast.Lambda(
                                    args=["x"],
                                    expr=ast.Call(
                                        name="multiSearchAnyCaseInsensitive",
                                        args=[ast.Field(chain=["x"]), ast.Constant(value=scalar_val)],
                                    ),
                                ),
                                col,
                            ],
                        )
                    )
                return ast.Not(
                    expr=ast.Call(
                        name="arrayExists",
                        args=[
                            ast.Lambda(
                                args=["x"],
                                expr=ast.Call(
                                    name="ilike",
                                    args=[ast.Field(chain=["x"]), ast.Constant(value=f"%{scalar_val}%")],
                                ),
                            ),
                            col,
                        ],
                    )
                )
            case PropertyOperator.REGEX:
                if isinstance(scalar_val, list):
                    scalar_val = "|".join(str(v) for v in scalar_val)
                return ast.Call(
                    name="arrayExists",
                    args=[
                        ast.Lambda(
                            args=["x"],
                            expr=ast.Call(name="match", args=[ast.Field(chain=["x"]), ast.Constant(value=scalar_val)]),
                        ),
                        col,
                    ],
                )
            case PropertyOperator.NOT_REGEX:
                if isinstance(scalar_val, list):
                    scalar_val = "|".join(str(v) for v in scalar_val)
                return ast.Not(
                    expr=ast.Call(
                        name="arrayExists",
                        args=[
                            ast.Lambda(
                                args=["x"],
                                expr=ast.Call(
                                    name="match", args=[ast.Field(chain=["x"]), ast.Constant(value=scalar_val)]
                                ),
                            ),
                            col,
                        ],
                    )
                )
            case PropertyOperator.IS_SET:
                return ast.Call(name="notEmpty", args=[col])
            case PropertyOperator.IS_NOT_SET:
                return ast.Call(name="empty", args=[col])
            case _:
                raise ValueError(f"Unsupported operator for sessions v3 array predicate: {f.operator}")

    @staticmethod
    def _merged_array_col(table: str, column: str) -> ast.Expr:
        """Aggregate a SimpleAggregateFunction array column across parts.

        Uses arrayDistinct(arrayFlatten(groupArray(col))) which is the same
        pattern the sessions v3 HogQL schema uses (collect_array_field)."""
        return ast.Call(
            name="arrayDistinct",
            args=[
                ast.Call(
                    name="arrayFlatten",
                    args=[ast.Call(name="groupArray", args=[ast.Field(chain=[table, column])])],
                )
            ],
        )

    def _sessions_v3_subquery(self) -> ast.SelectQuery | None:
        """Build a subquery against raw_sessions_v3 that returns session IDs matching
        the intercepted property and event name filters.

        Because raw_sessions_v3 is an AggregatingMergeTree, multiple parts may exist
        per session. Array columns (hosts, emails, urls, event_names) must be merged
        via aggregation before filtering, so predicates go in HAVING."""
        if not self._sessions_v3_property_filters and not self._sessions_v3_event_names:
            return None

        table = "raw_sessions_v3"
        where_exprs: list[ast.Expr] = [
            ast.CompareOperation(
                op=ast.CompareOperationOp.Eq,
                left=ast.Field(chain=[table, "team_id"]),
                right=ast.Constant(value=self._team.pk),
            ),
        ]

        # Date range pruning (safe in WHERE — these are SimpleAggregateFunction min/max).
        # Use max_timestamp for the lower bound to prune sessions that ended before the
        # query window, and min_timestamp for the upper bound (session started before date_to).
        query_date_from = self.query_date_range.date_from()
        if query_date_from:
            where_exprs.append(
                ast.CompareOperation(
                    op=ast.CompareOperationOp.GtEq,
                    left=ast.Field(chain=[table, "max_timestamp"]),
                    right=ast.Constant(value=query_date_from - timedelta(days=1)),
                )
            )
        query_date_to = self.query_date_range.date_to()
        if query_date_to:
            where_exprs.append(
                ast.CompareOperation(
                    op=ast.CompareOperationOp.LtEq,
                    left=ast.Field(chain=[table, "min_timestamp"]),
                    right=ast.Constant(value=query_date_to + timedelta(days=1)),
                )
            )

        # HAVING predicates: array columns must be aggregated before filtering
        having_exprs: list[ast.Expr] = []

        for f in self._sessions_v3_property_filters:
            merged_col = self._merged_array_col(table, f.column)
            having_exprs.append(self._property_filter_to_array_expr(f, col_override=merged_col))

        if self._sessions_v3_event_names:
            merged_event_names = self._merged_array_col(table, "event_names")
            for event_name in self._sessions_v3_event_names:
                having_exprs.append(
                    ast.Call(
                        name="has",
                        args=[merged_event_names, ast.Constant(value=event_name)],
                    )
                )

        # Convert session_id_v7 (UInt128) → string UUID
        session_id_expr = ast.Call(
            name="toString",
            args=[uuid_uint128_to_uuid_expr(ast.Field(chain=[table, "session_id_v7"]))],
        )

        return ast.SelectQuery(
            select=[ast.Alias(alias="session_id", expr=session_id_expr)],
            select_from=ast.JoinExpr(table=ast.Field(chain=[table])),
            where=ast.And(exprs=where_exprs),
            having=ast.And(exprs=having_exprs) if having_exprs else None,
            group_by=[
                ast.Field(chain=[table, "session_id_v7"]),
                ast.Field(chain=[table, "session_timestamp"]),
                ast.Field(chain=[table, "team_id"]),
            ],
        )

    @tracer.start_as_current_span("SessionRecordingListFromQuery._where_predicates")
    def _where_predicates(self) -> Union[ast.And, ast.Or]:
        exprs: list[ast.Expr] = []

        if self._query.distinct_ids:
            exprs.append(
                ast.CompareOperation(
                    op=ast.CompareOperationOp.In,
                    left=ast.Field(chain=["distinct_id"]),
                    right=ast.Constant(value=self._query.distinct_ids),
                )
            )
        else:
            person_id_compare_operation = PersonsIdCompareOperation(self._team, self._query).get_operation()
            if person_id_compare_operation:
                exprs.append(person_id_compare_operation)

        # we check for session_ids type not for truthiness since we want to allow empty lists
        if isinstance(self._query.session_ids, list):
            exprs.append(
                ast.CompareOperation(
                    op=ast.CompareOperationOp.In,
                    left=ast.Field(chain=["session_id"]),
                    right=ast.Constant(value=self._query.session_ids),
                )
            )

        query_date_from = self.query_date_range.date_from()
        if query_date_from:
            exprs.append(
                ast.CompareOperation(
                    op=ast.CompareOperationOp.GtEq,
                    left=ast.Field(chain=["s", "min_first_timestamp"]),
                    right=ast.Constant(value=query_date_from),
                )
            )

        query_date_to = self.query_date_range.date_to()
        if query_date_to:
            exprs.append(
                ast.CompareOperation(
                    op=ast.CompareOperationOp.LtEq,
                    left=ast.Field(chain=["s", "min_first_timestamp"]),
                    right=ast.Constant(value=query_date_to),
                )
            )

        optional_exprs: list[ast.Expr] = []

        # Use sessions v3 subquery for eligible filters instead of scanning events table
        sessions_v3_subquery = self._sessions_v3_subquery()
        if sessions_v3_subquery:
            optional_exprs.append(
                ast.CompareOperation(
                    op=ast.CompareOperationOp.GlobalIn,
                    left=ast.Field(chain=["s", "session_id"]),
                    right=sessions_v3_subquery,
                )
            )

        # if in PoE mode then we should be pushing person property queries into here
        events_sub_queries = ReplayFiltersEventsSubQuery(
            self._team, self._query, self._allow_event_property_expansion
        ).get_queries_for_session_id_matching()
        for events_sub_query in events_sub_queries:
            optional_exprs.append(
                ast.CompareOperation(
                    # this hits the distributed events table from the distributed session_replay_events table
                    # so we should use GlobalIn
                    # see https://clickhouse.com/docs/en/sql-reference/operators/in#distributed-subqueries
                    op=ast.CompareOperationOp.GlobalIn,
                    left=ast.Field(chain=["s", "session_id"]),
                    right=events_sub_query,
                )
            )

        # we want to avoid a join to persons since we don't ever need to select from them,
        # so we create our own persons sub query here
        # if PoE mode is on then this will be handled in the events subquery, and we don't need to do anything here
        person_subquery = PersonsPropertiesSubQuery(self._team, self._query).get_query()
        if person_subquery:
            optional_exprs.append(
                ast.CompareOperation(
                    op=ast.CompareOperationOp.In,
                    left=ast.Field(chain=["s", "distinct_id"]),
                    right=person_subquery,
                )
            )

        cohort_subquery = CohortPropertyGroupsSubQuery(self._team, self._query).get_query()
        if cohort_subquery:
            optional_exprs.append(
                ast.CompareOperation(
                    op=ast.CompareOperationOp.In,
                    left=ast.Field(chain=["s", "distinct_id"]),
                    right=cohort_subquery,
                )
            )

        remaining_properties = _strip_person_and_event_and_cohort_properties(self._query.properties)
        if remaining_properties:
            capture_exception(UnexpectedQueryProperties(remaining_properties))
            optional_exprs.append(property_to_expr(remaining_properties, team=self._team, scope="replay"))

        if self._query.console_log_filters:
            console_logs_subquery = ast.SelectQuery(
                select=[ast.Field(chain=["log_source_id"])],
                select_from=ast.JoinExpr(table=ast.Field(chain=["console_logs_log_entries"])),
                where=property_to_expr(
                    # convert to a property group so we can insert the correct operand
                    PropertyGroupFilterValue(
                        type=(
                            FilterLogicalOperator.AND_ if self.property_operand == "AND" else FilterLogicalOperator.OR_
                        ),
                        values=self._query.console_log_filters,
                    ),
                    team=self._team,
                ),
            )

            optional_exprs.append(
                ast.CompareOperation(
                    op=ast.CompareOperationOp.In,
                    left=ast.Field(chain=["session_id"]),
                    right=console_logs_subquery,
                )
            )

        if optional_exprs:
            exprs.append(self.wrapped_with_query_operand(exprs=optional_exprs))

        return ast.And(exprs=exprs)

    @tracer.start_as_current_span("SessionRecordingListFromQuery._having_predicates")
    def _having_predicates(self) -> ast.Expr | None:
        exprs: list[ast.Expr] = [
            ast.CompareOperation(
                op=ast.CompareOperationOp.GtEq,
                left=ast.Field(chain=["expiry_time"]),
                right=ast.Constant(value=datetime.now(UTC)),
            ),
            # Exclude deleted recordings (crypto shredding)
            ast.CompareOperation(
                op=ast.CompareOperationOp.Eq,
                left=ast.Call(name="max", args=[ast.Field(chain=["s", "is_deleted"])]),
                right=ast.Constant(value=0),
            ),
        ]

        if self._query.having_predicates:
            exprs.append(property_to_expr(self._query.having_predicates, team=self._team, scope="replay"))

        return ast.And(exprs=exprs)
