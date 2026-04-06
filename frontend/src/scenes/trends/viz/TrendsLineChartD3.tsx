import { useValues } from 'kea'
import { useCallback, useMemo } from 'react'

import { buildTheme } from 'lib/charts/utils/theme'
import { LineChart } from 'lib/hog-charts'
import type { TooltipContext } from 'lib/hog-charts/core/types'
import { buildTrendsConfig, buildTrendsSeries } from 'lib/hog-charts/transforms/trends'
import { insightLogic } from 'scenes/insights/insightLogic'
import { teamLogic } from 'scenes/teamLogic'

import { themeLogic } from '~/layout/navigation-3000/themeLogic'
import { groupsModel } from '~/models/groupsModel'
import { InsightVizNode } from '~/queries/schema/schema-general'
import { QueryContext } from '~/queries/types'

import { InsightEmptyState } from '../../insights/EmptyStates'
import { trendsDataLogic } from '../trendsDataLogic'
import { TrendsTooltip } from './TrendsTooltip'

interface TrendsLineChartD3Props {
    context?: QueryContext<InsightVizNode>
}

export function TrendsLineChartD3({ context }: TrendsLineChartD3Props): JSX.Element | null {
    const { isDarkModeOn } = useValues(themeLogic)
    const theme = useMemo(() => buildTheme(), [isDarkModeOn])
    const { insightProps } = useValues(insightLogic)

    const {
        indexedResults,
        display,
        interval,
        showPercentStackView,
        supportsPercentStackView,
        yAxisScaleType,
        goalLines,
        getTrendsColor,
        currentPeriodResult,
        breakdownFilter,
        insightData,
        trendsFilter,
        formula,
        isStickiness,
        labelGroupType,
    } = useValues(trendsDataLogic(insightProps))
    const { timezone, baseCurrency } = useValues(teamLogic)
    const { aggregationLabel } = useValues(groupsModel)

    const isPercentStackView = !!showPercentStackView && !!supportsPercentStackView
    const resolvedGroupTypeLabel =
        context?.groupTypeLabel ??
        (labelGroupType === 'people'
            ? 'people'
            : labelGroupType === 'none'
              ? ''
              : aggregationLabel(labelGroupType).plural)

    const labels = currentPeriodResult?.labels ?? []

    const hogSeries = useMemo(
        () => buildTrendsSeries(indexedResults ?? [], display, getTrendsColor),
        [indexedResults, display, getTrendsColor]
    )

    const hasData = indexedResults && indexedResults[0]?.data && indexedResults.some((r) => r.count !== 0)

    const chartConfig = useMemo(
        () =>
            buildTrendsConfig({
                interval,
                days: currentPeriodResult?.days ?? [],
                timezone,
                yAxisScaleType,
                isPercentStackView,
                goalLines,
            }),
        [interval, currentPeriodResult?.days, timezone, yAxisScaleType, isPercentStackView, goalLines]
    )

    const formatCompareLabel = context?.formatCompareLabel
    const renderTooltip = useCallback(
        (ctx: TooltipContext) => (
            <TrendsTooltip
                context={ctx}
                timezone={timezone}
                interval={interval ?? undefined}
                breakdownFilter={breakdownFilter ?? undefined}
                dateRange={insightData?.resolved_date_range ?? undefined}
                trendsFilter={trendsFilter}
                formula={formula}
                showPercentView={isStickiness}
                isPercentStackView={isPercentStackView}
                baseCurrency={baseCurrency}
                groupTypeLabel={resolvedGroupTypeLabel}
                formatCompareLabel={formatCompareLabel}
            />
        ),
        [
            timezone,
            interval,
            breakdownFilter,
            insightData?.resolved_date_range,
            trendsFilter,
            formula,
            isStickiness,
            isPercentStackView,
            baseCurrency,
            resolvedGroupTypeLabel,
            formatCompareLabel,
        ]
    )

    if (!hasData) {
        return <InsightEmptyState heading={context?.emptyStateHeading} detail={context?.emptyStateDetail} />
    }

    return <LineChart series={hogSeries} labels={labels} config={chartConfig} theme={theme} tooltip={renderTooltip} />
}
