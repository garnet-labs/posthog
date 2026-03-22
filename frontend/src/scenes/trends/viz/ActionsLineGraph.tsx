import { type DeepPartial } from 'chart.js/dist/types/utils'
import { useValues } from 'kea'

import { Chart, ChartType, LegendOptions, defaults } from 'lib/Chart'
import { createXAxisTickCallback } from 'lib/charts/utils/dates'
import { insightAlertsLogic } from 'lib/components/Alerts/insightAlertsLogic'
import { DateDisplay } from 'lib/components/DateDisplay'
import { PropertyKeyInfo } from 'lib/components/PropertyKeyInfo'
import { LineChart as HogLineChart } from 'lib/hog-charts'
import type { Series as HogSeries } from 'lib/hog-charts'
import { ciRanges, movingAverage } from 'lib/statistics'
import { capitalizeFirstLetter, hexToRGBA } from 'lib/utils'
import { insightLogic } from 'scenes/insights/insightLogic'
import { teamLogic } from 'scenes/teamLogic'
import { datasetToActorsQuery } from 'scenes/trends/viz/datasetToActorsQuery'

import { GoalLine } from '~/queries/schema/schema-general'
import { ChartDisplayType, ChartParams, GraphType } from '~/types'

import { InsightEmptyState } from '../../insights/EmptyStates'
import { LineGraph } from '../../insights/views/LineGraph/LineGraph'
import { openPersonsModal } from '../persons-modal/PersonsModal'
import { trendsDataLogic } from '../trendsDataLogic'
import type { IndexedTrendResult } from '../types'

export function ActionsLineGraph({
    inSharedMode = false,
    showPersonsModal = true,
    context,
}: ChartParams): JSX.Element | null {
    const { insightProps, insight } = useValues(insightLogic)

    const {
        indexedResults,
        labelGroupType,
        incompletenessOffsetFromEnd,
        formula,
        display,
        interval,
        showValuesOnSeries,
        showPercentStackView,
        supportsPercentStackView,
        trendsFilter,
        lifecycleFilter,
        isLifecycle,
        isStickiness,
        hasPersonsModal,
        showLegend,
        querySource,
        yAxisScaleType,
        showMultipleYAxes,
        goalLines,
        insightData,
        showConfidenceIntervals,
        confidenceLevel,
        showTrendLines,
        showMovingAverage,
        movingAverageIntervals,
        getTrendsColor,
        currentPeriodResult,
    } = useValues(trendsDataLogic(insightProps))
    const { weekStartDay, timezone } = useValues(teamLogic)

    const { alertThresholdLines, alertAnomalyPoints } = useValues(
        insightAlertsLogic({ insightId: insight.id!, insightLogicProps: insightProps })
    )

    const labels = currentPeriodResult?.labels ?? []

    const shortenLifecycleLabels = (s: string | undefined): string => {
        const labelParts = s?.split(' - ')
        const label = labelParts?.[labelParts.length - 1]

        return capitalizeFirstLetter(label ?? s ?? 'None')
    }

    const legend: DeepPartial<LegendOptions<ChartType>> = {
        display: false,
    }
    if (isLifecycle && !!showLegend) {
        legend.display = true
        legend.labels = {
            generateLabels: (chart: Chart) => {
                const labelElements = defaults.plugins.legend.labels.generateLabels(chart)
                labelElements.forEach((elt) => {
                    elt.text = shortenLifecycleLabels(elt.text)
                })
                return labelElements
            },
        }
    }

    if (
        !(
            indexedResults &&
            indexedResults[0]?.data &&
            indexedResults.filter((result: IndexedTrendResult) => result.count !== 0).length > 0
        )
    ) {
        return <InsightEmptyState heading={context?.emptyStateHeading} detail={context?.emptyStateDetail} />
    }

    const finalDatasets = indexedResults.flatMap((originalDataset: IndexedTrendResult, index: number) => {
        const yAxisID = showMultipleYAxes && index > 0 ? `y${index}` : 'y'
        const mainSeries = { ...originalDataset, yAxisID }
        const datasets = [mainSeries]
        const color = getTrendsColor(originalDataset)

        if (showConfidenceIntervals) {
            const [lower, upper] = ciRanges(originalDataset.data, confidenceLevel / 100)

            const lowerCIBound = {
                ...originalDataset,
                label: `${originalDataset.label} (CI lower)`,
                action: {
                    ...originalDataset.action,
                    name: `${originalDataset.label} (CI lower)`,
                },
                data: lower,
                borderColor: color,
                backgroundColor: 'transparent',
                pointRadius: 0,
                borderWidth: 0,
                hideTooltip: true,
                yAxisID,
            }
            const upperCIBound = {
                ...originalDataset,
                label: `${originalDataset.label} (CI upper)`,
                action: {
                    ...originalDataset.action,
                    name: `${originalDataset.label} (CI upper)`,
                },
                data: upper,
                borderColor: color,
                backgroundColor: hexToRGBA(color, 0.2),
                pointRadius: 0,
                borderWidth: 0,
                fill: '-1',
                hideTooltip: true,
                yAxisID,
            }
            datasets.push(lowerCIBound, upperCIBound)
        }

        if (showMovingAverage) {
            const movingAverageData = movingAverage(originalDataset.data, movingAverageIntervals)
            const movingAverageDataset = {
                ...originalDataset,
                label: `${originalDataset.label} (Moving avg)`,
                action: {
                    ...originalDataset.action,
                    name: `${originalDataset.label} (Moving avg)`,
                },
                data: movingAverageData,
                borderColor: color,
                backgroundColor: 'transparent',
                pointRadius: 0,
                borderWidth: 2,
                borderDash: [10, 3],
                hideTooltip: true,
                yAxisID,
            }
            datasets.push(movingAverageDataset)
        }
        return datasets
    })

    const isLineDisplay =
        display !== ChartDisplayType.ActionsBar && display !== ChartDisplayType.ActionsUnstackedBar && !isLifecycle

    if (isLineDisplay) {
        const hogSeries: HogSeries[] = indexedResults
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
            <HogLineChart
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

    return (
        <LineGraph
            data-attr="trend-line-graph"
            type={GraphType.Bar}
            datasets={finalDatasets}
            labels={labels}
            inSharedMode={inSharedMode}
            labelGroupType={labelGroupType}
            showPersonsModal={showPersonsModal}
            trendsFilter={trendsFilter}
            formula={formula}
            showValuesOnSeries={showValuesOnSeries}
            showPercentView={isStickiness}
            showPercentStackView={showPercentStackView}
            supportsPercentStackView={supportsPercentStackView}
            isStacked={
                isLifecycle ? (lifecycleFilter?.stacked ?? true) : display !== ChartDisplayType.ActionsUnstackedBar
            }
            yAxisScaleType={yAxisScaleType}
            showMultipleYAxes={showMultipleYAxes}
            showTrendLines={showTrendLines}
            tooltip={
                isLifecycle
                    ? {
                          altTitle: 'Users',
                          altRightTitle: (_, date) => {
                              return date
                          },
                          renderSeries: (_, datum) => {
                              return shortenLifecycleLabels(datum.label)
                          },
                      }
                    : {
                          groupTypeLabel: context?.groupTypeLabel,
                          filter: (s) => !s.hideTooltip,
                          formatCompareLabel: context?.formatCompareLabel,
                      }
            }
            isInProgress={!isStickiness && incompletenessOffsetFromEnd < 0}
            isArea={display === ChartDisplayType.ActionsAreaGraph}
            incompletenessOffsetFromEnd={incompletenessOffsetFromEnd}
            legend={legend}
            hideAnnotations={inSharedMode}
            goalLines={[...alertThresholdLines, ...(goalLines || [])]}
            anomalyPoints={alertAnomalyPoints}
            onDateRangeZoom={context?.onDateRangeZoom}
            onClick={
                context?.onDataPointClick || (showPersonsModal && hasPersonsModal)
                    ? (payload) => {
                          const { index, points } = payload

                          const dataset = points.referencePoint.dataset
                          if (!dataset) {
                              return
                          }

                          const day = dataset.action?.days?.[index] ?? dataset?.days?.[index] ?? ''
                          const label = dataset?.label ?? dataset?.labels?.[index] ?? ''

                          if (context?.onDataPointClick) {
                              context.onDataPointClick(
                                  {
                                      breakdown: dataset.breakdownValues?.[index],
                                      compare: dataset.compareLabels?.[index] || undefined,
                                      day,
                                  },
                                  indexedResults[0]
                              )
                              return
                          }

                          const title = isStickiness ? (
                              <>
                                  <PropertyKeyInfo value={label || ''} disablePopover /> stickiness on{' '}
                                  {interval || 'day'} {day}
                              </>
                          ) : (
                              (label: string) => (
                                  <>
                                      {label} on{' '}
                                      <DateDisplay
                                          interval={interval || 'day'}
                                          resolvedDateRange={insightData?.resolved_date_range}
                                          timezone={timezone}
                                          weekStartDay={weekStartDay}
                                          date={day?.toString() || ''}
                                      />
                                  </>
                              )
                          )

                          openPersonsModal({
                              title,
                              query: datasetToActorsQuery({ dataset, query: querySource!, day }),
                              additionalSelect:
                                  isLifecycle || isStickiness
                                      ? {}
                                      : {
                                            value_at_data_point: 'event_count',
                                            matched_recordings: 'matched_recordings',
                                        },
                              orderBy: isLifecycle || isStickiness ? undefined : ['event_count DESC, actor_id DESC'],
                          })
                      }
                    : undefined
            }
        />
    )
}
