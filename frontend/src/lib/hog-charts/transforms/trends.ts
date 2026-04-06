import { createXAxisTickCallback } from 'lib/charts/utils/dates'

import { GoalLine as SchemaGoalLine } from '~/queries/schema/schema-general'
import { ChartDisplayType, IntervalType, LifecycleToggle, TrendResult } from '~/types'

import type { LineChartConfig, Series } from '../core/types'

// Breakdown sentinel values — duplicated from scenes/insights/utils to avoid
// coupling the transform layer to scene-level code.
const BREAKDOWN_OTHER_STRING_LABEL = '$$_posthog_breakdown_other_$$'
const BREAKDOWN_OTHER_NUMERIC_LABEL = 9007199254740991
const BREAKDOWN_NULL_STRING_LABEL = '$$_posthog_breakdown_null_$$'
const BREAKDOWN_NULL_NUMERIC_LABEL = 9007199254740990

export interface IndexedTrendResult extends TrendResult {
    id: number
    seriesIndex: number
    colorIndex: number
}

/** Sort and index raw trend results for visualization. */
export function indexTrendResults(
    results: TrendResult[],
    display: ChartDisplayType | undefined | null,
    lifecycleFilter?: { toggledLifecycles?: LifecycleToggle[] } | null
): IndexedTrendResult[] {
    const defaultLifecyclesOrder = ['new', 'resurrecting', 'returning', 'dormant']
    let indexed = results.map((result, index) => ({ ...result, seriesIndex: index }))

    // want the previous bars to show before current bars
    if (display === ChartDisplayType.ActionsUnstackedBar && indexed.some((x) => x.compare)) {
        indexed.sort((a, b) => {
            if (a.compare_label === b.compare_label) {
                return 0
            }
            if (a.compare_label === 'previous') {
                return -1
            }
            if (b.compare_label === 'previous') {
                return 1
            }
            return 0
        })
    } else if (display && (display === ChartDisplayType.ActionsBarValue || display === ChartDisplayType.ActionsPie)) {
        indexed.sort((a, b) => {
            const aValue =
                a.breakdown_value === BREAKDOWN_OTHER_STRING_LABEL
                    ? -BREAKDOWN_OTHER_NUMERIC_LABEL
                    : a.breakdown_value === BREAKDOWN_NULL_STRING_LABEL
                      ? -BREAKDOWN_NULL_NUMERIC_LABEL
                      : a.aggregated_value
            const bValue =
                b.breakdown_value === BREAKDOWN_OTHER_STRING_LABEL
                    ? -BREAKDOWN_OTHER_NUMERIC_LABEL
                    : b.breakdown_value === BREAKDOWN_NULL_STRING_LABEL
                      ? -BREAKDOWN_NULL_NUMERIC_LABEL
                      : b.aggregated_value
            return bValue - aValue
        })
    } else if (lifecycleFilter) {
        if (lifecycleFilter.toggledLifecycles) {
            indexed = indexed.filter((result) =>
                lifecycleFilter.toggledLifecycles!.includes(String(result.status) as LifecycleToggle)
            )
        }

        indexed = indexed.sort(
            (a, b) =>
                defaultLifecyclesOrder.indexOf(String(b.status)) - defaultLifecyclesOrder.indexOf(String(a.status))
        )
    }

    const colorIndexMap = new Map<string, number>()
    indexed
        .slice()
        .sort((a, b) => (a.action?.order ?? 0) - (b.action?.order ?? 0))
        .forEach((item) => {
            const key = `${item.label}_${item.action?.order}_${item?.breakdown_value}`
            if (!colorIndexMap.has(key)) {
                colorIndexMap.set(key, colorIndexMap.size)
            }
        })

    return indexed.map((item, index) => {
        const key = `${item.label}_${item.action?.order}_${item?.breakdown_value}`
        const colorIndex = colorIndexMap.get(key) ?? 0
        return { ...item, colorIndex, id: index }
    })
}

/** Map indexed trend results to hog-charts Series[]. */
export function buildTrendsSeries(
    indexedResults: IndexedTrendResult[],
    display: ChartDisplayType | undefined | null,
    getColor: (result: IndexedTrendResult) => string
): Series[] {
    return indexedResults.map((r) => ({
        key: `${r.id}`,
        label: r.label ?? '',
        data: r.data,
        color: getColor(r),
        fillArea: display === ChartDisplayType.ActionsAreaGraph,
        meta: {
            action: r.action,
            breakdown_value: r.breakdown_value,
            compare_label: r.compare_label,
            days: r.days,
            // Fall back to the pre-filter index (r.id) so ordering is stable when earlier series are dropped.
            order: r.action?.order ?? r.id,
            filter: r.filter,
        },
    }))
}

export interface BuildTrendsConfigOptions {
    interval: IntervalType | undefined | null
    days: (string | number)[]
    timezone: string
    yAxisScaleType: string | null | undefined
    isPercentStackView: boolean
    goalLines: SchemaGoalLine[] | undefined | null
}

/** Build a LineChartConfig from trends query options. */
export function buildTrendsConfig({
    interval,
    days,
    timezone,
    yAxisScaleType,
    isPercentStackView,
    goalLines,
}: BuildTrendsConfigOptions): LineChartConfig {
    const xTickFormatter = createXAxisTickCallback({
        interval: interval ?? 'day',
        allDays: days,
        timezone,
    })
    return {
        showGrid: true,
        showCrosshair: true,
        pinnableTooltip: true,
        yScaleType: yAxisScaleType === 'log10' ? 'log' : 'linear',
        percentStackView: isPercentStackView,
        xTickFormatter,
        goalLines: goalLines?.map((g) => ({
            value: g.value,
            label: g.label ?? undefined,
            borderColor: g.borderColor ?? undefined,
        })),
    }
}
