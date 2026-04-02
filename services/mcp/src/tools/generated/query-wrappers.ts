// AUTO-GENERATED from services/mcp/definitions/query-wrappers.yaml + schema.json — do not edit
import { z } from 'zod'

import { createQueryWrapper } from '@/tools/query-wrapper-factory'
import type { ZodObjectAny } from '@/tools/types'

// --- Shared Zod schemas generated from schema.json ---

const integer = z.coerce.number().int()

const AssistantGroupMultipleBreakdownFilter = z.object({
    group_type_index: z.union([integer, z.null()]).optional(),
    property: z.string(),
    type: z.literal('group').default('group'),
})

const AssistantEventMultipleBreakdownFilterType = z.enum([
    'cohort',
    'person',
    'event',
    'event_metadata',
    'session',
    'hogql',
    'data_warehouse_person_property',
    'revenue_analytics',
])

const AssistantGenericMultipleBreakdownFilter = z.object({
    property: z.string(),
    type: AssistantEventMultipleBreakdownFilterType,
})

const AssistantMultipleBreakdownFilter = z.union([
    AssistantGroupMultipleBreakdownFilter,
    AssistantGenericMultipleBreakdownFilter,
])

const AssistantTrendsBreakdownFilter = z.object({
    breakdown_limit: integer.default(25).optional(),
    breakdowns: z.array(AssistantMultipleBreakdownFilter),
})

const CompareFilter = z.object({
    compare: z.coerce.boolean().default(false).optional(),
    compare_to: z.string().optional(),
})

const AssistantDateRange = z.object({
    date_from: z.string(),
    date_to: z.string().nullable().optional(),
})

const AssistantDurationRange = z.object({
    date_from: z.string(),
})

const AssistantDateRangeFilter = z.union([AssistantDateRange, AssistantDurationRange])

const IntervalType = z.enum(['second', 'minute', 'hour', 'day', 'week', 'month'])

const AssistantStringOrBooleanValuePropertyFilterOperator = z.enum([
    'exact',
    'is_not',
    'icontains',
    'not_icontains',
    'regex',
    'not_regex',
])

const AssistantGenericPropertyFilterType = z.enum(['event', 'person', 'session', 'feature'])

const AssistantNumericValuePropertyFilterOperator = z.enum(['exact', 'gt', 'lt'])

const AssistantArrayPropertyFilterOperator = z.enum(['exact', 'is_not'])

const AssistantDateTimePropertyFilterOperator = z.enum(['is_date_exact', 'is_date_before', 'is_date_after'])

const AssistantSetPropertyFilterOperator = z.enum(['is_set', 'is_not_set'])

const AssistantGenericPropertyFilter = z.union([
    z.object({
        key: z.string(),
        operator: AssistantStringOrBooleanValuePropertyFilterOperator,
        type: AssistantGenericPropertyFilterType,
        value: z.string(),
    }),
    z.object({
        key: z.string(),
        operator: AssistantNumericValuePropertyFilterOperator,
        type: AssistantGenericPropertyFilterType,
        value: z.coerce.number(),
    }),
    z.object({
        key: z.string(),
        operator: AssistantArrayPropertyFilterOperator,
        type: AssistantGenericPropertyFilterType,
        value: z.array(z.string()),
    }),
    z.object({
        key: z.string(),
        operator: AssistantDateTimePropertyFilterOperator,
        type: AssistantGenericPropertyFilterType,
        value: z.string(),
    }),
    z.object({
        key: z.string(),
        operator: AssistantSetPropertyFilterOperator,
        type: AssistantGenericPropertyFilterType,
    }),
])

const AssistantGroupPropertyFilter = z.union([
    z.object({
        group_type_index: integer,
        key: z.string(),
        operator: AssistantStringOrBooleanValuePropertyFilterOperator,
        type: z.literal('group').default('group'),
        value: z.string(),
    }),
    z.object({
        group_type_index: integer,
        key: z.string(),
        operator: AssistantNumericValuePropertyFilterOperator,
        type: z.literal('group').default('group'),
        value: z.coerce.number(),
    }),
    z.object({
        group_type_index: integer,
        key: z.string(),
        operator: AssistantArrayPropertyFilterOperator,
        type: z.literal('group').default('group'),
        value: z.array(z.string()),
    }),
    z.object({
        group_type_index: integer,
        key: z.string(),
        operator: AssistantDateTimePropertyFilterOperator,
        type: z.literal('group').default('group'),
        value: z.string(),
    }),
    z.object({
        group_type_index: integer,
        key: z.string(),
        operator: AssistantSetPropertyFilterOperator,
        type: z.literal('group').default('group'),
    }),
])

const AssistantCohortPropertyFilter = z.object({
    key: z.literal('id').default('id'),
    operator: z.literal('in').default('in'),
    type: z.literal('cohort').default('cohort'),
    value: integer,
})

const AssistantElementPropertyFilter = z.union([
    z.object({
        key: z.enum(['tag_name', 'text', 'href', 'selector']),
        operator: AssistantStringOrBooleanValuePropertyFilterOperator,
        type: z.literal('element').default('element'),
        value: z.string(),
    }),
    z.object({
        key: z.enum(['tag_name', 'text', 'href', 'selector']),
        operator: AssistantNumericValuePropertyFilterOperator,
        type: z.literal('element').default('element'),
        value: z.coerce.number(),
    }),
    z.object({
        key: z.enum(['tag_name', 'text', 'href', 'selector']),
        operator: AssistantArrayPropertyFilterOperator,
        type: z.literal('element').default('element'),
        value: z.array(z.string()),
    }),
    z.object({
        key: z.enum(['tag_name', 'text', 'href', 'selector']),
        operator: AssistantDateTimePropertyFilterOperator,
        type: z.literal('element').default('element'),
        value: z.string(),
    }),
    z.object({
        key: z.enum(['tag_name', 'text', 'href', 'selector']),
        operator: AssistantSetPropertyFilterOperator,
        type: z.literal('element').default('element'),
    }),
])

const AssistantHogQLPropertyFilter = z.object({
    key: z.string(),
    type: z.literal('hogql').default('hogql'),
})

const AssistantFlagPropertyFilter = z.object({
    key: z.string(),
    operator: z.literal('flag_evaluates_to').default('flag_evaluates_to'),
    type: z.literal('flag').default('flag'),
    value: z.union([z.coerce.boolean(), z.string()]),
})

const AssistantPropertyFilter = z.union([
    AssistantGenericPropertyFilter,
    AssistantGroupPropertyFilter,
    AssistantCohortPropertyFilter,
    AssistantElementPropertyFilter,
    AssistantHogQLPropertyFilter,
    AssistantFlagPropertyFilter,
])

const BaseMathType = z.enum([
    'total',
    'dau',
    'weekly_active',
    'monthly_active',
    'unique_session',
    'first_time_for_user',
    'first_matching_event_for_user',
])

const FunnelMathType = z.enum(['total', 'first_time_for_user', 'first_time_for_user_with_filters'])

const PropertyMathType = z.enum(['avg', 'sum', 'min', 'max', 'median', 'p75', 'p90', 'p95', 'p99'])

const CountPerActorMathType = z.enum([
    'avg_count_per_actor',
    'min_count_per_actor',
    'max_count_per_actor',
    'median_count_per_actor',
    'p75_count_per_actor',
    'p90_count_per_actor',
    'p95_count_per_actor',
    'p99_count_per_actor',
])

const GroupMathType = z.literal('unique_group')

const HogQLMathType = z.literal('hogql')

const ExperimentMetricMathType = z.enum([
    'total',
    'sum',
    'unique_session',
    'min',
    'max',
    'avg',
    'dau',
    'unique_group',
    'hogql',
])

const CalendarHeatmapMathType = z.enum(['total', 'dau'])

const MathType = z.union([
    BaseMathType,
    FunnelMathType,
    PropertyMathType,
    CountPerActorMathType,
    GroupMathType,
    HogQLMathType,
    ExperimentMetricMathType,
    CalendarHeatmapMathType,
])

const AssistantTrendsEventsNode = z.object({
    custom_name: z.string().optional(),
    event: z.string().nullable().optional(),
    kind: z.literal('EventsNode').default('EventsNode'),
    math: MathType.optional(),
    math_group_type_index: z.union([z.literal(0), z.literal(1), z.literal(2), z.literal(3), z.literal(4)]).optional(),
    math_hogql: z.string().optional(),
    math_multiplier: z.coerce.number().optional(),
    math_property: z.string().optional(),
    math_property_type: z.string().optional(),
    name: z.string().optional(),
    optionalInFunnel: z.coerce.boolean().optional(),
    properties: z.array(AssistantPropertyFilter).optional(),
    version: z.coerce.number().optional(),
})

const AssistantTrendsActionsNode = z.object({
    custom_name: z.string().optional(),
    id: integer,
    kind: z.literal('ActionsNode').default('ActionsNode'),
    math: MathType.optional(),
    math_group_type_index: z.union([z.literal(0), z.literal(1), z.literal(2), z.literal(3), z.literal(4)]).optional(),
    math_hogql: z.string().optional(),
    math_multiplier: z.coerce.number().optional(),
    math_property: z.string().optional(),
    math_property_type: z.string().optional(),
    name: z.string(),
    optionalInFunnel: z.coerce.boolean().optional(),
    properties: z.array(AssistantPropertyFilter).optional(),
    version: z.coerce.number().optional(),
})

const AggregationAxisFormat = z.enum([
    'numeric',
    'duration',
    'duration_ms',
    'percentage',
    'percentage_scaled',
    'currency',
    'short',
])

const TrendsFormulaNode = z.object({
    custom_name: z.string().optional(),
    formula: z.string(),
})

const AssistantTrendsFilter = z.object({
    aggregationAxisFormat: AggregationAxisFormat.default('numeric').optional(),
    aggregationAxisPostfix: z.string().optional(),
    aggregationAxisPrefix: z.string().optional(),
    decimalPlaces: z.coerce.number().optional(),
    display: z
        .enum([
            'Auto',
            'ActionsLineGraph',
            'ActionsBar',
            'ActionsUnstackedBar',
            'ActionsAreaGraph',
            'ActionsLineGraphCumulative',
            'BoldNumber',
            'ActionsPie',
            'ActionsBarValue',
            'ActionsTable',
            'WorldMap',
            'CalendarHeatmap',
            'TwoDimensionalHeatmap',
            'BoxPlot',
        ])
        .default('ActionsLineGraph')
        .optional(),
    formulaNodes: z.array(TrendsFormulaNode).optional(),
    showAlertThresholdLines: z.coerce.boolean().default(false).optional(),
    showLabelsOnSeries: z.coerce.boolean().default(false).optional(),
    showLegend: z.coerce.boolean().default(false).optional(),
    showMultipleYAxes: z.coerce.boolean().default(false).optional(),
    showPercentStackView: z.coerce.boolean().default(false).optional(),
    showValuesOnSeries: z.coerce.boolean().default(false).optional(),
    smoothingIntervals: integer.default(1).optional(),
    yAxisScaleType: z.enum(['log10', 'linear']).default('linear').optional(),
})

const AssistantTrendsQuery = z.object({
    aggregation_group_type_index: z.union([integer, z.null()]).describe('Groups aggregation').optional(),
    breakdownFilter: AssistantTrendsBreakdownFilter.describe(
        'Breakdowns are used to segment data by property values of maximum three properties. They divide all defined trends series to multiple subseries based on the values of the property. Include breakdowns **only when they are essential to directly answer the user’s question**. You must not add breakdowns if the question can be addressed without additional segmentation. Always use the minimum set of breakdowns needed to answer the question. When using breakdowns, you must:\n- **Identify the property group** and name for each breakdown.\n- **Provide the property name** for each breakdown.\n- **Validate that the property value accurately reflects the intended criteria**. Examples of using breakdowns:\n- page views trend by country: you need to find a property such as `$geoip_country_code` and set it as a breakdown.\n- number of users who have completed onboarding by an organization: you need to find a property such as `organization name` and set it as a breakdown.'
    ).optional(),
    compareFilter: CompareFilter.describe('Compare to date range').optional(),
    dateRange: AssistantDateRangeFilter.describe('Date range for the query').optional(),
    filterTestAccounts: z.coerce
        .boolean()
        .describe('Exclude internal and test users by applying the respective filters')
        .default(false)
        .optional(),
    interval: IntervalType.describe('Granularity of the response. Can be one of `hour`, `day`, `week` or `month`')
        .default('day')
        .optional(),
    kind: z.literal('TrendsQuery').default('TrendsQuery'),
    properties: z.array(AssistantPropertyFilter).describe('Property filters for all series').default([]).optional(),
    series: z
        .array(z.union([AssistantTrendsEventsNode, AssistantTrendsActionsNode]))
        .describe('Events or actions to include. Prioritize the more popular and fresh events and actions.'),
    trendsFilter: AssistantTrendsFilter.describe('Properties specific to the trends insight').optional(),
})

const AssistantFunnelsBreakdownType = z.enum(['person', 'event', 'group', 'session'])

const AssistantFunnelsBreakdownFilter = z.object({
    breakdown: z.string(),
    breakdown_group_type_index: z.union([integer, z.null()]).optional(),
    breakdown_limit: integer.default(25).optional(),
    breakdown_type: AssistantFunnelsBreakdownType.default('event'),
})

const BreakdownAttributionType = z.enum(['first_touch', 'last_touch', 'all_events', 'step'])

const AssistantFunnelsExclusionEventsNode = z.object({
    event: z.string(),
    funnelFromStep: integer,
    funnelToStep: integer,
    kind: z.literal('EventsNode').default('EventsNode'),
})

const StepOrderValue = z.enum(['strict', 'unordered', 'ordered'])

const FunnelStepReference = z.enum(['total', 'previous'])

const FunnelVizType = z.enum(['steps', 'time_to_convert', 'trends', 'flow'])

const FunnelConversionWindowTimeUnit = z.enum(['second', 'minute', 'hour', 'day', 'week', 'month'])

const FunnelLayout = z.enum(['horizontal', 'vertical'])

const AssistantFunnelsFilter = z.object({
    binCount: z.coerce.number().int().optional(),
    breakdownAttributionType: BreakdownAttributionType.default('first_touch').optional(),
    breakdownAttributionValue: z.coerce.number().int().optional(),
    exclusions: z.array(AssistantFunnelsExclusionEventsNode).default([]).optional(),
    funnelAggregateByHogQL: z
        .union([z.literal('properties.$session_id'), z.literal(null)])
        .default(null)
        .optional(),
    funnelOrderType: StepOrderValue.default('ordered').optional(),
    funnelStepReference: FunnelStepReference.default('total').optional(),
    funnelVizType: FunnelVizType.default('steps').optional(),
    funnelWindowInterval: integer.default(14).optional(),
    funnelWindowIntervalUnit: FunnelConversionWindowTimeUnit.default('day').optional(),
    layout: FunnelLayout.default('vertical').optional(),
})

const AssistantFunnelsMath = z.enum(['first_time_for_user', 'first_time_for_user_with_filters'])

const AssistantFunnelsEventsNode = z.object({
    custom_name: z.string().optional(),
    event: z.string(),
    kind: z.literal('EventsNode').default('EventsNode'),
    math: AssistantFunnelsMath.optional(),
    properties: z.array(AssistantPropertyFilter).optional(),
    version: z.coerce.number().optional(),
})

const AssistantFunnelsActionsNode = z.object({
    id: z.coerce.number(),
    kind: z.literal('ActionsNode').default('ActionsNode'),
    math: AssistantFunnelsMath.optional(),
    name: z.string(),
    properties: z.array(AssistantPropertyFilter).optional(),
    version: z.coerce.number().optional(),
})

const AssistantFunnelsNode = z.union([AssistantFunnelsEventsNode, AssistantFunnelsActionsNode])

const AssistantFunnelsQuery = z.object({
    aggregation_group_type_index: integer
        .describe(
            'Use this field to define the aggregation by a specific group from the provided group mapping, which is NOT users or sessions.'
        )
        .optional(),
    breakdownFilter: AssistantFunnelsBreakdownFilter.describe(
        'A breakdown is used to segment data by a single property value. They divide all defined funnel series into multiple subseries based on the values of the property. Include a breakdown **only when it is essential to directly answer the user’s question**. You must not add a breakdown if the question can be addressed without additional segmentation. When using breakdowns, you must:\n- **Identify the property group** and name for a breakdown.\n- **Provide the property name** for a breakdown.\n- **Validate that the property value accurately reflects the intended criteria**. Examples of using a breakdown:\n- page views to sign up funnel by country: you need to find a property such as `$geoip_country_code` and set it as a breakdown.\n- conversion rate of users who have completed onboarding after signing up by an organization: you need to find a property such as `organization name` and set it as a breakdown.'
    ).optional(),
    dateRange: AssistantDateRangeFilter.describe('Date range for the query').optional(),
    filterTestAccounts: z.coerce
        .boolean()
        .describe('Exclude internal and test users by applying the respective filters')
        .default(false)
        .optional(),
    funnelsFilter: AssistantFunnelsFilter.describe('Properties specific to the funnels insight').optional(),
    interval: IntervalType.describe(
        'Granularity of the response. Can be one of `hour`, `day`, `week` or `month`'
    ).optional(),
    kind: z.literal('FunnelsQuery').default('FunnelsQuery'),
    properties: z.array(AssistantPropertyFilter).describe('Property filters for all series').default([]).optional(),
    series: z
        .array(AssistantFunnelsNode)
        .describe('Events or actions to include. Prioritize the more popular and fresh events and actions.'),
})

const RetentionPeriod = z.enum(['Hour', 'Day', 'Week', 'Month'])

const RetentionType = z.enum(['retention_recurring', 'retention_first_time', 'retention_first_ever_occurrence'])

const AssistantRetentionEventsNode = z.object({
    custom_name: z.string().optional(),
    name: z.string(),
    properties: z.array(AssistantPropertyFilter).optional(),
    type: z.literal('events').default('events'),
})

const AssistantRetentionActionsNode = z.object({
    id: z.coerce.number(),
    name: z.string(),
    properties: z.array(AssistantPropertyFilter).optional(),
    type: z.literal('actions').default('actions'),
})

const AssistantRetentionEntity = z.union([AssistantRetentionEventsNode, AssistantRetentionActionsNode])

const AssistantRetentionFilter = z.object({
    aggregationProperty: z.string().optional(),
    aggregationPropertyType: z.enum(['event', 'person']).default('event').optional(),
    aggregationType: z.enum(['count', 'sum', 'avg']).default('count').optional(),
    cumulative: z.coerce.boolean().optional(),
    meanRetentionCalculation: z.enum(['simple', 'weighted', 'none']).optional(),
    minimumOccurrences: integer.optional(),
    period: RetentionPeriod.default('Day').optional(),
    retentionCustomBrackets: z.array(z.coerce.number()).optional(),
    retentionReference: z.enum(['total', 'previous']).optional(),
    retentionType: RetentionType.optional(),
    returningEntity: AssistantRetentionEntity,
    targetEntity: AssistantRetentionEntity,
    timeWindowMode: z.enum(['strict_calendar_dates', '24_hour_windows']).optional(),
    totalIntervals: integer.default(8).optional(),
})

const AssistantRetentionQuery = z.object({
    aggregation_group_type_index: z.union([integer, z.null()]).describe('Groups aggregation').optional(),
    dateRange: AssistantDateRangeFilter.describe('Date range for the query').optional(),
    filterTestAccounts: z.coerce
        .boolean()
        .describe('Exclude internal and test users by applying the respective filters')
        .default(false)
        .optional(),
    kind: z.literal('RetentionQuery').default('RetentionQuery'),
    properties: z.array(AssistantPropertyFilter).describe('Property filters for all series').default([]).optional(),
    retentionFilter: AssistantRetentionFilter.describe('Properties specific to the retention insight'),
})

const AssistantStickinessEventsNode = z.object({
    custom_name: z.string().optional(),
    event: z.string().nullable().optional(),
    kind: z.literal('EventsNode').default('EventsNode'),
    math: MathType.optional(),
    math_group_type_index: z.union([z.literal(0), z.literal(1), z.literal(2), z.literal(3), z.literal(4)]).optional(),
    math_hogql: z.string().optional(),
    math_multiplier: z.coerce.number().optional(),
    math_property: z.string().optional(),
    math_property_type: z.string().optional(),
    name: z.string().optional(),
    properties: z.array(AssistantPropertyFilter).optional(),
})

const AssistantStickinessActionsNode = z.object({
    custom_name: z.string().optional(),
    id: integer,
    kind: z.literal('ActionsNode').default('ActionsNode'),
    math: MathType.optional(),
    math_group_type_index: z.union([z.literal(0), z.literal(1), z.literal(2), z.literal(3), z.literal(4)]).optional(),
    math_hogql: z.string().optional(),
    math_multiplier: z.coerce.number().optional(),
    math_property: z.string().optional(),
    math_property_type: z.string().optional(),
    name: z.string(),
    properties: z.array(AssistantPropertyFilter).optional(),
})

const AssistantStickinessNode = z.union([AssistantStickinessEventsNode, AssistantStickinessActionsNode])

const StickinessComputationMode = z.enum(['non_cumulative', 'cumulative'])

const AssistantStickinessDisplayType = z.enum(['ActionsLineGraph', 'ActionsBar', 'ActionsAreaGraph'])

const StickinessOperator = z.enum(['gte', 'lte', 'exact'])

const StickinessCriteria = z.object({
    operator: StickinessOperator,
    value: integer,
})

const AssistantStickinessFilter = z.object({
    computedAs: StickinessComputationMode.default('non_cumulative').optional(),
    display: AssistantStickinessDisplayType.default('ActionsLineGraph').optional(),
    showLegend: z.coerce.boolean().default(false).optional(),
    showValuesOnSeries: z.coerce.boolean().default(false).optional(),
    stickinessCriteria: StickinessCriteria.optional(),
})

const AssistantStickinessQuery = z.object({
    aggregation_group_type_index: z.union([integer, z.null()]).describe('Groups aggregation').optional(),
    compareFilter: CompareFilter.describe(
        'Compare to date range. When enabled, shows the current and previous period side by side.'
    ).optional(),
    dateRange: AssistantDateRangeFilter.describe('Date range for the query').optional(),
    filterTestAccounts: z.coerce
        .boolean()
        .describe('Exclude internal and test users by applying the respective filters')
        .default(false)
        .optional(),
    interval: IntervalType.describe(
        'Granularity of the response. Can be one of `hour`, `day`, `week` or `month`. This determines what counts as one "interval" for stickiness measurement. For example, with `day` interval over a 30-day range, the X-axis shows 1 through 30 days, and each bar/point shows how many users performed the event on exactly that many days.'
    )
        .default('day')
        .optional(),
    intervalCount: integer
        .describe(
            'How many base intervals comprise one stickiness period. Defaults to 1. For example, `interval: "day"` with `intervalCount: 7` groups by 7-day periods.'
        )
        .optional(),
    kind: z.literal('StickinessQuery').default('StickinessQuery'),
    properties: z.array(AssistantPropertyFilter).describe('Property filters for all series').default([]).optional(),
    series: z
        .array(AssistantStickinessNode)
        .describe(
            'Events or actions to include. Each series measures how many intervals (e.g. days) within the date range a user performed the event. Prioritize the more popular and fresh events and actions. When the `math` field is omitted on a series, it defaults to counting unique persons.'
        ),
    stickinessFilter: AssistantStickinessFilter.describe('Properties specific to the stickiness insight').optional(),
})

const PathType = z.enum(['$pageview', '$screen', 'custom_event', 'hogql'])

const AssistantPathCleaningFilter = z.object({
    alias: z.string(),
    regex: z.string(),
})

const AssistantPathsFilter = z.object({
    edgeLimit: integer.default(50).optional(),
    endPoint: z.string().optional(),
    excludeEvents: z.array(z.string()).default([]).optional(),
    includeEventTypes: z.array(PathType).optional(),
    localPathCleaningFilters: z.array(AssistantPathCleaningFilter).default([]).optional(),
    maxEdgeWeight: integer.optional(),
    minEdgeWeight: integer.optional(),
    pathGroupings: z.array(z.string()).default([]).optional(),
    pathsHogQLExpression: z.string().optional(),
    startPoint: z.string().optional(),
    stepLimit: integer.default(5).optional(),
})

const AssistantPathsQuery = z.object({
    aggregation_group_type_index: z.union([integer, z.null()]).describe('Groups aggregation').optional(),
    dateRange: AssistantDateRangeFilter.describe('Date range for the query').optional(),
    filterTestAccounts: z.coerce
        .boolean()
        .describe('Exclude internal and test users by applying the respective filters')
        .default(false)
        .optional(),
    kind: z.literal('PathsQuery').default('PathsQuery'),
    pathsFilter: AssistantPathsFilter.describe(
        'Properties specific to the paths insight. Paths show the most common sequences of events or pages that users navigate through, helping identify popular user flows and drop-off points.'
    ),
    properties: z.array(AssistantPropertyFilter).describe('Property filters for all series').default([]).optional(),
})

const LifecycleToggle = z.enum(['new', 'resurrecting', 'returning', 'dormant'])

const AssistantLifecycleFilter = z.object({
    showLegend: z.coerce.boolean().default(false).optional(),
    showValuesOnSeries: z.coerce.boolean().default(false).optional(),
    stacked: z.coerce.boolean().default(true).optional(),
    toggledLifecycles: z.array(LifecycleToggle).optional(),
})

const AssistantLifecycleEventsNode = z.object({
    custom_name: z.string().optional(),
    event: z.string().nullable().optional(),
    kind: z.literal('EventsNode').default('EventsNode'),
    name: z.string().optional(),
    properties: z.array(AssistantPropertyFilter).optional(),
})

const AssistantLifecycleActionsNode = z.object({
    custom_name: z.string().optional(),
    id: integer,
    kind: z.literal('ActionsNode').default('ActionsNode'),
    name: z.string(),
    properties: z.array(AssistantPropertyFilter).optional(),
})

const AssistantLifecycleSeriesNode = z.union([AssistantLifecycleEventsNode, AssistantLifecycleActionsNode])

const AssistantLifecycleQuery = z.object({
    aggregation_group_type_index: z.union([integer, z.null()]).describe('Groups aggregation').optional(),
    dateRange: AssistantDateRangeFilter.describe('Date range for the query').optional(),
    filterTestAccounts: z.coerce
        .boolean()
        .describe('Exclude internal and test users by applying the respective filters')
        .default(false)
        .optional(),
    interval: IntervalType.describe('Granularity of the response. Can be one of `hour`, `day`, `week` or `month`')
        .default('day')
        .optional(),
    kind: z.literal('LifecycleQuery').default('LifecycleQuery'),
    lifecycleFilter: AssistantLifecycleFilter.describe('Properties specific to the lifecycle insight').optional(),
    properties: z.array(AssistantPropertyFilter).describe('Property filters for all series').default([]).optional(),
    series: z
        .array(AssistantLifecycleSeriesNode)
        .describe('Event or action to analyze. Lifecycle insights only support a single series.'),
})

const AssistantTracesQuery = z.object({
    dateRange: AssistantDateRangeFilter.describe('Date range for the query.').optional(),
    filterSupportTraces: z.coerce.boolean().describe('Exclude support impersonation traces.').default(false).optional(),
    filterTestAccounts: z.coerce
        .boolean()
        .describe('Exclude internal and test users by applying the respective filters.')
        .default(true)
        .optional(),
    groupKey: z.string().describe('Filter traces by group key. Requires `groupTypeIndex` to be set.').optional(),
    groupTypeIndex: integer.describe('Group type index when filtering by group.').optional(),
    kind: z.literal('TracesQuery').default('TracesQuery'),
    limit: integer.describe('Maximum number of traces to return.').default(100).optional(),
    offset: integer.describe('Number of traces to skip for pagination.').default(0).optional(),
    personId: z.string().describe('Filter traces by a specific person UUID.').optional(),
    properties: z
        .array(AssistantPropertyFilter)
        .describe(
            'Property filters to narrow results. Use event properties like `$ai_model`, `$ai_provider`, `$ai_trace_id`, etc. to filter traces.'
        )
        .default([])
        .optional(),
    randomOrder: z.coerce
        .boolean()
        .describe(
            'Use random ordering instead of timestamp DESC. Useful for representative sampling to avoid recency bias.'
        )
        .default(false)
        .optional(),
})

const AssistantTraceQuery = z.object({
    dateRange: AssistantDateRangeFilter.describe('Date range for the query.').optional(),
    kind: z.literal('TraceQuery').default('TraceQuery'),
    properties: z
        .array(AssistantPropertyFilter)
        .describe('Property filters to narrow events within the trace.')
        .default([])
        .optional(),
    traceId: z
        .string()
        .describe('The trace ID to fetch (the `id` field from a trace in `query-llm-traces-list` results).'),
})

// --- Tool registrations ---

export const GENERATED_TOOLS: Record<string, ReturnType<typeof createQueryWrapper<ZodObjectAny>>> = {
    'query-trends': createQueryWrapper({
        name: 'query-trends',
        schema: AssistantTrendsQuery,
        kind: 'TrendsQuery',
        uiResourceUri: 'ui://posthog/query-results.html',
    }),
    'query-funnel': createQueryWrapper({
        name: 'query-funnel',
        schema: AssistantFunnelsQuery,
        kind: 'FunnelsQuery',
        uiResourceUri: 'ui://posthog/query-results.html',
    }),
    'query-retention': createQueryWrapper({
        name: 'query-retention',
        schema: AssistantRetentionQuery,
        kind: 'RetentionQuery',
        uiResourceUri: 'ui://posthog/query-results.html',
    }),
    'query-stickiness': createQueryWrapper({
        name: 'query-stickiness',
        schema: AssistantStickinessQuery,
        kind: 'StickinessQuery',
        uiResourceUri: 'ui://posthog/query-results.html',
    }),
    'query-paths': createQueryWrapper({
        name: 'query-paths',
        schema: AssistantPathsQuery,
        kind: 'PathsQuery',
        uiResourceUri: 'ui://posthog/query-results.html',
    }),
    'query-lifecycle': createQueryWrapper({
        name: 'query-lifecycle',
        schema: AssistantLifecycleQuery,
        kind: 'LifecycleQuery',
        uiResourceUri: 'ui://posthog/query-results.html',
    }),
    'query-llm-traces-list': createQueryWrapper({
        name: 'query-llm-traces-list',
        schema: AssistantTracesQuery,
        kind: 'TracesQuery',
        responseFormat: 'json',
    }),
    'query-llm-trace': createQueryWrapper({
        name: 'query-llm-trace',
        schema: AssistantTraceQuery,
        kind: 'TraceQuery',
        responseFormat: 'json',
    }),
}
