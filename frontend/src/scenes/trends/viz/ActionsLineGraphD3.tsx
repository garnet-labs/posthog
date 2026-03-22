import { useValues } from 'kea'

import { createXAxisTickCallback } from 'lib/charts/utils/dates'
import { LineChart } from 'lib/hog-charts'
import type { Series } from 'lib/hog-charts'
import { insightLogic } from 'scenes/insights/insightLogic'
import { teamLogic } from 'scenes/teamLogic'

import { GoalLine } from '~/queries/schema/schema-general'
import { ChartDisplayType, ChartParams } from '~/types'

import { InsightEmptyState } from '../../insights/EmptyStates'
import { trendsDataLogic } from '../trendsDataLogic'
import type { IndexedTrendResult } from '../types'

export function ActionsLineGraphD3({ context }: ChartParams): JSX.Element | null {
    const { insightProps } = useValues(insightLogic)

    const {
        indexedResults,
        incompletenessOffsetFromEnd,
        display,
        interval,
        showValuesOnSeries,
        showPercentStackView,
        supportsPercentStackView,
        isStickiness,
        yAxisScaleType,
        showMultipleYAxes,
        goalLines,
        showTrendLines,
        getTrendsColor,
        currentPeriodResult,
    } = useValues(trendsDataLogic(insightProps))
    const { timezone } = useValues(teamLogic)

    const labels = currentPeriodResult?.labels ?? []

    if (
        !(
            indexedResults &&
            indexedResults[0]?.data &&
            indexedResults.filter((result: IndexedTrendResult) => result.count !== 0).length > 0
        )
    ) {
        return <InsightEmptyState heading={context?.emptyStateHeading} detail={context?.emptyStateDetail} />
    }

    const hogSeries: Series[] = indexedResults
        .filter((r: IndexedTrendResult) => r.count !== 0)
        .map((r: IndexedTrendResult) => ({
            key: `${r.id}`,
            label: r.label ?? '',
            data: r.data,
            color: getTrendsColor(r),
            fillArea: display === ChartDisplayType.ActionsAreaGraph,
            yAxisId: showMultipleYAxes && r.id > 0 ? `y${r.id}` : undefined,
        }))

    const incompleteIdx =
        !isStickiness && incompletenessOffsetFromEnd < 0 ? labels.length + incompletenessOffsetFromEnd : undefined

    const xTickFormatter = createXAxisTickCallback({
        interval: interval ?? 'day',
        allDays: currentPeriodResult?.days ?? [],
        timezone,
    })

    return (
        <LineChart
            series={hogSeries}
            labels={labels}
            xTickFormatter={xTickFormatter}
            showGrid
            showCrosshair
            showDataLabels={!!showValuesOnSeries}
            showTrendLines={!!showTrendLines}
            yScaleType={yAxisScaleType === 'log10' ? 'log' : 'linear'}
            multipleYAxes={!!showMultipleYAxes}
            percentStackView={!!showPercentStackView && !!supportsPercentStackView}
            goalLines={goalLines?.map((g: GoalLine) => ({
                value: g.value,
                label: g.label ?? undefined,
                borderColor: g.borderColor ?? undefined,
            }))}
            incompleteFromIndex={incompleteIdx}
            hideXAxis={false}
            hideYAxis={false}
            renderTooltip={(ctx) => (
                <div
                    style={{
                        background: 'var(--bg-surface-tooltip)',
                        color: 'var(--text-primary)',
                        padding: '8px 12px',
                        borderRadius: 6,
                        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                        fontSize: 13,
                    }}
                >
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>{ctx.label}</div>
                    {ctx.seriesData.map((s) => (
                        <div key={s.series.key} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                            <span
                                style={{
                                    width: 8,
                                    height: 8,
                                    borderRadius: '50%',
                                    backgroundColor: s.color,
                                    display: 'inline-block',
                                }}
                            />
                            <span>{s.series.label}:</span>
                            <strong>{s.value.toLocaleString()}</strong>
                        </div>
                    ))}
                </div>
            )}
        />
    )
}
