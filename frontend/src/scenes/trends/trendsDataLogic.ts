import { actions, connect, kea, key, listeners, path, props, reducers, selectors } from 'kea'

import { DataColorTheme, DataColorToken } from 'lib/colors'
import { dayjs } from 'lib/dayjs'
import { indexTrendResults } from 'lib/hog-charts/transforms/trends'
import type { IndexedTrendResult } from 'lib/hog-charts/transforms/trends'
import { isMultiSeriesFormula } from 'lib/utils'
import { dashboardLogic } from 'scenes/dashboard/dashboardLogic'
import { getColorFromToken } from 'scenes/dataThemeLogic'
import { insightVizDataLogic } from 'scenes/insights/insightVizDataLogic'
import { keyForInsightLogicProps } from 'scenes/insights/sharedUtils'
import {
    getTrendDatasetKey,
    getTrendResultCustomization,
    getTrendResultCustomizationColorToken,
    getTrendResultCustomizationKey,
} from 'scenes/insights/utils'

import {
    BreakdownFilter,
    EventsNode,
    InsightQueryNode,
    LifecycleQuery,
    MathType,
    ResultCustomization,
    ResultCustomizationBy,
    TrendsFilter,
    TrendsQuery,
} from '~/queries/schema/schema-general'
import { isValidBreakdown } from '~/queries/utils'
import {
    ChartDisplayType,
    CountPerActorMathType,
    HogQLMathType,
    InsightLogicProps,
    IntervalType,
    PropertyMathType,
    TrendAPIResponse,
    TrendResult,
} from '~/types'

import type { trendsDataLogicType } from './trendsDataLogicType'

export const RESULT_CUSTOMIZATION_DEFAULT = ResultCustomizationBy.Value

/** All math types that can result in non-whole numbers. */
const POSSIBLY_FRACTIONAL_MATH_TYPES: Set<MathType> = new Set(
    [CountPerActorMathType.Average as MathType]
        .concat(Object.values(HogQLMathType))
        .concat(Object.values(PropertyMathType))
)

export const INTERVAL_TO_DEFAULT_MOVING_AVERAGE_PERIOD: Record<IntervalType, number> = {
    second: 300,
    minute: 10,
    hour: 6,
    day: 7,
    week: 4,
    month: 3,
}

const DEFAULT_CONFIDENCE_LEVEL = 95

export const trendsDataLogic = kea<trendsDataLogicType>([
    props({} as InsightLogicProps),
    key(keyForInsightLogicProps('all_trends')),
    path((key) => ['scenes', 'trends', 'trendsDataLogic', key]),

    connect((props: InsightLogicProps) => ({
        values: [
            insightVizDataLogic(props),
            [
                'querySource',
                'insightData',
                'insightDataLoading',
                'series',
                'formula',
                'formulaNodes',
                'display',
                'goalLines',
                'compareFilter',
                'interval',
                'enabledIntervals',
                'breakdownFilter',
                'showValuesOnSeries',
                'showLabelOnSeries',
                'showPercentStackView',
                'supportsPercentStackView',
                'insightFilter',
                'trendsFilter',
                'lifecycleFilter',
                'stickinessFilter',
                'isTrends',
                'hasDataWarehouseSeries',
                'isLifecycle',
                'isStickiness',
                'isNonTimeSeriesDisplay',
                'isSingleSeriesOutput',
                'isSingleSeriesDefinition',
                'isBreakdownSeries',
                'hasLegend',
                'showLegend',
                'vizSpecificOptions',
                'yAxisScaleType',
                'showMultipleYAxes',
                'resultCustomizationBy as resultCustomizationByRaw',
                'getTheme',
                'theme',
            ],
        ],
        actions: [insightVizDataLogic(props), ['setInsightData', 'updateInsightFilter', 'updateBreakdownFilter']],
    })),

    actions({
        loadMoreBreakdownValues: true,
        setBreakdownValuesLoading: (loading: boolean) => ({ loading }),
        toggleResultHidden: (dataset: IndexedTrendResult) => ({ dataset }),
        toggleAllResultsHidden: (datasets: IndexedTrendResult[], hidden: boolean) => ({ datasets, hidden }),
        toggleOtherSeriesHidden: (dataset: IndexedTrendResult) => ({ dataset }),
        setHoveredDatasetIndex: (index: number | null) => ({ index }),
    }),

    reducers({
        breakdownValuesLoading: [
            false,
            {
                setBreakdownValuesLoading: (_, { loading }) => loading,
            },
        ],
        hoveredDatasetIndex: [
            null as number | null,
            {
                setHoveredDatasetIndex: (_, { index }) => index,
            },
        ],
    }),

    selectors(({ values, props }) => ({
        /** series within the trend insight on which user can set alerts */
        alertSeries: [
            (s) => [s.querySource],
            (queryNode: InsightQueryNode | null): EventsNode[] => {
                if (queryNode === null) {
                    return []
                }

                return (queryNode as TrendsQuery).series as EventsNode[]
            },
        ],

        results: [
            (s) => [s.insightData],
            (insightData: TrendAPIResponse | null): TrendResult[] => {
                if (insightData?.result && Array.isArray(insightData.result)) {
                    return insightData.result
                }
                return []
            },
        ],

        hasBreakdownMore: [
            (s) => [s.insightData, s.isTrends],
            (insightData, isTrends) => {
                if (!isTrends) {
                    return false
                }
                return !!insightData.hasMore
            },
        ],
        hasPersonsModal: [
            (s) => [s.formula, s.hasDataWarehouseSeries, s.isLifecycle, s.querySource],
            (formula, hasDataWarehouseSeries, isLifecycle, querySource) => {
                if (isMultiSeriesFormula(formula)) {
                    return false
                }

                if (!hasDataWarehouseSeries) {
                    return true
                }

                return isLifecycle && (querySource as LifecycleQuery | null)?.customAggregationTarget !== true
            },
        ],

        isBreakdownValid: [
            (s) => [s.breakdownFilter],
            (breakdownFilter: BreakdownFilter | null) => isValidBreakdown(breakdownFilter),
        ],

        indexedResults: [
            (s) => [s.results, s.display, s.lifecycleFilter],
            (results, display, lifecycleFilter): IndexedTrendResult[] =>
                indexTrendResults(results, display, lifecycleFilter),
        ],

        currentPeriodResult: [
            (s) => [s.indexedResults],
            (indexedResults: IndexedTrendResult[]): IndexedTrendResult | undefined =>
                indexedResults.find((r) => r.compare_label === 'current') ?? indexedResults[0],
        ],

        labelGroupType: [
            (s) => [s.series, s.querySource, s.isLifecycle],
            (series, querySource, isLifecycle): 'people' | 'none' | number => {
                // Find the commonly shared aggregation group index if there is one.
                let firstAggregationGroupTypeIndex: 'people' | 'none' | number | undefined | null
                if (isLifecycle) {
                    firstAggregationGroupTypeIndex = (querySource as LifecycleQuery)?.aggregation_group_type_index
                } else {
                    firstAggregationGroupTypeIndex = series?.[0]?.math_group_type_index
                    if (!series?.every((eOrA) => eOrA?.math_group_type_index === firstAggregationGroupTypeIndex)) {
                        return 'none' // mixed group types
                    }
                }

                return firstAggregationGroupTypeIndex ?? 'people'
            },
        ],

        incompletenessOffsetFromEnd: [
            (s) => [s.results, s.interval],
            (results, interval) => {
                // Returns negative number of points to paint over starting from end of array
                if (results[0]?.days === undefined) {
                    return 0
                }
                const startDate = dayjs()
                    .tz('utc', true)
                    .startOf(interval ?? 'd')
                const startIndex = results[0].days.findIndex((day: string) => {
                    return dayjs(day).tz('utc', true) >= startDate
                })

                if (startIndex !== undefined && startIndex !== -1) {
                    return startIndex - results[0].days.length
                }
                return 0
            },
        ],

        showConfidenceIntervals: [
            (s) => [s.trendsFilter, s.isTrends, s.hasDataWarehouseSeries, s.yAxisScaleType],
            (
                trendsFilter: TrendsFilter | undefined | null,
                isTrends: boolean,
                hasDataWarehouseSeries: boolean,
                yAxisScaleType: string | undefined
            ): boolean => {
                const isLinearScale = !yAxisScaleType || yAxisScaleType === 'linear'
                const display = trendsFilter?.display || ChartDisplayType.ActionsLineGraph
                const isLineGraph =
                    isTrends &&
                    !hasDataWarehouseSeries &&
                    [ChartDisplayType.ActionsLineGraph, ChartDisplayType.ActionsLineGraphCumulative].includes(display)

                return (trendsFilter?.showConfidenceIntervals && isLineGraph && isLinearScale) || false
            },
        ],

        showTrendLines: [
            (s) => [s.querySource, s.isTrends, s.hasDataWarehouseSeries, s.yAxisScaleType, s.trendsFilter],
            (
                querySource: InsightQueryNode | null,
                isTrends: boolean,
                hasDataWarehouseSeries: boolean,
                yAxisScaleType: string | undefined,
                trendsFilter: TrendsFilter | undefined | null
            ): boolean => {
                const isLinearScale = !yAxisScaleType || yAxisScaleType === 'linear'
                const display = trendsFilter?.display || ChartDisplayType.ActionsLineGraph
                const isLineGraph =
                    isTrends &&
                    !hasDataWarehouseSeries &&
                    [ChartDisplayType.ActionsLineGraph, ChartDisplayType.ActionsLineGraphCumulative].includes(display)

                return (
                    ((querySource as TrendsQuery)?.trendsFilter?.showTrendLines && isLineGraph && isLinearScale) ||
                    false
                )
            },
        ],

        showMovingAverage: [
            (s) => [s.trendsFilter, s.isTrends, s.hasDataWarehouseSeries, s.yAxisScaleType],
            (
                trendsFilter: TrendsFilter | undefined | null,
                isTrends: boolean,
                hasDataWarehouseSeries: boolean,
                yAxisScaleType: string | undefined
            ): boolean => {
                const isLinearScale = !yAxisScaleType || yAxisScaleType === 'linear'
                const display = trendsFilter?.display || ChartDisplayType.ActionsLineGraph
                const isLineGraph =
                    isTrends &&
                    !hasDataWarehouseSeries &&
                    [
                        ChartDisplayType.ActionsLineGraph,
                        ChartDisplayType.ActionsLineGraphCumulative,
                        ChartDisplayType.ActionsAreaGraph,
                    ].includes(display)

                return (trendsFilter?.showMovingAverage && isLineGraph && isLinearScale) || false
            },
        ],

        movingAverageIntervals: [
            (s) => [s.trendsFilter, s.interval],
            (trendsFilter: TrendsFilter | undefined | null, interval: IntervalType): number => {
                return trendsFilter?.movingAverageIntervals || INTERVAL_TO_DEFAULT_MOVING_AVERAGE_PERIOD[interval]
            },
        ],

        confidenceLevel: [
            (s) => [s.trendsFilter],
            (trendsFilter: TrendsFilter | undefined | null): number => {
                return trendsFilter?.confidenceLevel || DEFAULT_CONFIDENCE_LEVEL
            },
        ],

        pieChartVizOptions: [
            () => [() => values.vizSpecificOptions],
            (vizSpecificOptions) => vizSpecificOptions?.[ChartDisplayType.ActionsPie],
        ],

        mightContainFractionalNumbers: [
            (s) => [s.formula, s.series],
            (formula, series): boolean => {
                // Whether data points might contain fractional numbers, which involve extra display considerations,
                // such as rounding
                if (formula) {
                    return true
                }
                if (series) {
                    return series.some((s) => s.math && POSSIBLY_FRACTIONAL_MATH_TYPES.has(s.math))
                }
                return false
            },
        ],

        resultCustomizations: [
            (s) => [s.isTrends, s.isStickiness, s.trendsFilter, s.stickinessFilter],
            (isTrends, isStickiness, trendsFilter, stickinessFilter) => {
                if (isTrends) {
                    return trendsFilter?.resultCustomizations
                }
                if (isStickiness) {
                    return stickinessFilter?.resultCustomizations
                }
                return undefined
            },
        ],
        resultCustomizationBy: [
            (s) => [s.resultCustomizationByRaw],
            (resultCustomizationByRaw) => resultCustomizationByRaw || RESULT_CUSTOMIZATION_DEFAULT,
        ],

        getTrendsColorToken: [
            (s) => [s.resultCustomizationBy, s.resultCustomizations, s.getTheme, s.breakdownFilter, s.querySource],
            (resultCustomizationBy, resultCustomizations, getTheme, breakdownFilter, querySource) => {
                return (dataset: IndexedTrendResult): [DataColorTheme | null, DataColorToken | null] => {
                    // stringified breakdown value
                    const key = getTrendDatasetKey(dataset)
                    let breakdownValue = JSON.parse(key)['breakdown_value']
                    breakdownValue = Array.isArray(breakdownValue) ? breakdownValue.join('::') : breakdownValue

                    // dashboard color overrides
                    const logic = dashboardLogic.findMounted({ id: props.dashboardId })
                    const dashboardBreakdownColors = logic?.values.temporaryBreakdownColors
                    const colorOverride = dashboardBreakdownColors?.find(
                        (config) =>
                            config.breakdownValue === breakdownValue &&
                            config.breakdownType === (breakdownFilter?.breakdown_type ?? 'event')
                    )

                    if (colorOverride?.colorToken) {
                        // use the dashboard theme, or fallback to the default theme
                        const dashboardTheme = logic?.values.dataColorTheme || getTheme(undefined)
                        return [dashboardTheme, colorOverride.colorToken]
                    }

                    // use the dashboard theme, or fallback to the insight theme, or the default theme
                    const theme = logic?.values.dataColorTheme || getTheme(querySource?.dataColorTheme)
                    if (!theme) {
                        return [null, null]
                    }

                    return [
                        theme,
                        getTrendResultCustomizationColorToken(
                            resultCustomizationBy,
                            resultCustomizations,
                            theme,
                            dataset
                        ),
                    ]
                }
            },
        ],
        getTrendsColor: [
            (s) => [s.getTrendsColorToken],
            (getTrendsColorToken) => {
                return (dataset: IndexedTrendResult) => {
                    const [colorTheme, colorToken] = getTrendsColorToken(dataset)
                    return colorTheme && colorToken ? getColorFromToken(colorTheme, colorToken) : '#000000'
                }
            },
        ],
        getTrendsHidden: [
            (s) => [s.resultCustomizationBy, s.resultCustomizations],
            (resultCustomizationBy, resultCustomizations) => {
                return (dataset: IndexedTrendResult): boolean => {
                    const resultCustomization = getTrendResultCustomization(
                        resultCustomizationBy,
                        dataset,
                        resultCustomizations
                    )
                    return resultCustomization?.hidden || false
                }
            },
        ],

        areAllSeriesVisible: [
            (s) => [s.indexedResults, s.getTrendsHidden],
            (indexedResults, getTrendsHidden): boolean => indexedResults.every((d) => !getTrendsHidden(d)),
        ],

        showLegendIsolateSeriesItem: [
            (s) => [s.indexedResults, s.getTrendsHidden],
            (indexedResults, getTrendsHidden): boolean =>
                indexedResults.length > 0 && !indexedResults.every((d) => getTrendsHidden(d)),
        ],

        legendSeriesIsolationMenuEligible: [
            (s) => [s.indexedResults],
            (indexedResults: IndexedTrendResult[]): boolean => indexedResults.length > 1,
        ],

        getIsOnlyVisibleSeriesInLegend: [
            (s) => [s.indexedResults, s.resultCustomizationBy, s.getTrendsHidden],
            (indexedResults, resultCustomizationBy, getTrendsHidden) => {
                if (indexedResults.length < 2) {
                    return (): boolean => false
                }

                const visibleKeys = new Set(
                    indexedResults
                        .filter((r) => !getTrendsHidden(r))
                        .map((r) => getTrendResultCustomizationKey(resultCustomizationBy, r))
                )
                const soloKey = visibleKeys.size === 1 ? [...visibleKeys][0] : null

                return (dataset: IndexedTrendResult): boolean =>
                    soloKey !== null &&
                    !getTrendsHidden(dataset) &&
                    getTrendResultCustomizationKey(resultCustomizationBy, dataset) === soloKey
            },
        ],
    })),

    listeners(({ actions, values }) => ({
        toggleResultHidden: ({ dataset }) => {
            const resultCustomizationKey = getTrendResultCustomizationKey(values.resultCustomizationBy, dataset)
            const resultCustomization = getTrendResultCustomization(
                values.resultCustomizationBy,
                dataset,
                values.resultCustomizations
            )
            actions.updateInsightFilter({
                resultCustomizations: {
                    ...values.resultCustomizations,
                    [resultCustomizationKey]: {
                        ...resultCustomization,
                        assignmentBy: values.resultCustomizationBy,
                        hidden: !resultCustomization?.hidden,
                    },
                },
            } as Partial<TrendsFilter>)
        },
        toggleAllResultsHidden: ({ datasets, hidden }) => {
            const resultCustomizations: Record<string, ResultCustomization> = { ...values.resultCustomizations }
            for (const dataset of datasets) {
                const resultCustomizationKey = getTrendResultCustomizationKey(values.resultCustomizationBy, dataset)
                const existing = getTrendResultCustomization(
                    values.resultCustomizationBy,
                    dataset,
                    values.resultCustomizations
                )
                resultCustomizations[resultCustomizationKey] = {
                    ...existing,
                    assignmentBy: values.resultCustomizationBy,
                    hidden: hidden,
                }
            }

            actions.updateInsightFilter({
                resultCustomizations,
            } as Partial<TrendsFilter>)
        },
        toggleOtherSeriesHidden: ({ dataset }) => {
            const { indexedResults, resultCustomizationBy, resultCustomizations, getTrendsHidden } = values
            if (indexedResults.length < 2) {
                return
            }

            const clickedKey = getTrendResultCustomizationKey(resultCustomizationBy, dataset)
            const others = indexedResults.filter(
                (d) => getTrendResultCustomizationKey(resultCustomizationBy, d) !== clickedKey
            )
            const isSoloMode = others.length > 0 && !getTrendsHidden(dataset) && others.every((d) => getTrendsHidden(d))

            const next: Record<string, ResultCustomization> = { ...resultCustomizations }

            if (isSoloMode) {
                for (const r of indexedResults) {
                    const key = getTrendResultCustomizationKey(resultCustomizationBy, r)
                    const existing = getTrendResultCustomization(resultCustomizationBy, r, resultCustomizations)
                    next[key] = {
                        ...existing,
                        assignmentBy: values.resultCustomizationBy,
                        hidden: false,
                    }
                }
            } else {
                for (const r of indexedResults) {
                    const key = getTrendResultCustomizationKey(resultCustomizationBy, r)
                    const existing = getTrendResultCustomization(resultCustomizationBy, r, resultCustomizations)
                    const isClicked = key === clickedKey
                    next[key] = {
                        ...existing,
                        assignmentBy: values.resultCustomizationBy,
                        hidden: !isClicked,
                    }
                }
            }

            actions.updateInsightFilter({
                resultCustomizations: next,
            } as Partial<TrendsFilter>)
        },
    })),
])
