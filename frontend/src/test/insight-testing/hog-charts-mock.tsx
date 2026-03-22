/**
 * Mock for lib/hog-charts that captures HogLineChart props into the same
 * shared capture array used by the Chart.js mock. This lets getChart() and
 * waitForChart() work identically regardless of which renderer is active.
 */
import React, { useEffect, useRef } from 'react'

import type { CapturedChartConfig } from './captured-charts'
import { pushCapturedChart } from './captured-charts'

type ChartDataset = NonNullable<NonNullable<CapturedChartConfig['data']>['datasets']>[number]

// ---- Minimal type stubs matching lib/hog-charts exports ----

interface Series {
    key: string
    label: string
    data: number[]
    color: string
    yAxisId?: string
    fillArea?: boolean
    fillOpacity?: number
    dashPattern?: number[]
    hidden?: boolean
    pointRadius?: number
}

interface GoalLine {
    value: number
    label?: string
    borderColor?: string
    position?: 'start' | 'end'
}

interface TooltipContext {
    dataIndex: number
    label: string
    seriesData: { series: Series; value: number; color: string }[]
    position: { x: number; y: number }
    canvasBounds: DOMRect
}

interface PointClickData {
    seriesIndex: number
    dataIndex: number
    series: Series
    value: number
    label: string
    crossSeriesData: { series: Series; value: number }[]
}

interface LineChartProps {
    series: Series[]
    labels: string[]
    yScaleType?: 'linear' | 'log'
    multipleYAxes?: boolean
    percentStackView?: boolean
    xTickFormatter?: (value: string, index: number) => string | null
    yTickFormatter?: (value: number) => string
    renderTooltip?: (context: TooltipContext) => React.ReactNode
    onTooltipShow?: (context: TooltipContext) => void
    onTooltipHide?: () => void
    onPointClick?: (data: PointClickData) => void
    onRangeSelect?: (startIndex: number, endIndex: number) => void
    showGrid?: boolean
    showCrosshair?: boolean
    showDataLabels?: boolean
    dataLabelFormatter?: (value: number, seriesIndex: number) => string
    showTrendLines?: boolean
    goalLines?: GoalLine[]
    incompleteFromIndex?: number
    hideXAxis?: boolean
    hideYAxis?: boolean
    className?: string
}

/** Convert HogLineChart props into a CapturedChartConfig so the shared getChart() API works. */
function propsToCapturedChartConfig(props: LineChartProps): CapturedChartConfig {
    const datasets: ChartDataset[] = props.series.map((s) => ({
        label: s.label,
        data: s.data,
        hidden: s.hidden ?? false,
        borderColor: s.color,
        backgroundColor: s.fillArea ? s.color : 'transparent',
        yAxisID: s.yAxisId,
    }))

    const scales: NonNullable<CapturedChartConfig['options']>['scales'] = {
        x: {
            display: !props.hideXAxis,
            type: 'point',
            stacked: false,
            position: 'bottom',
            ticks: props.xTickFormatter
                ? { callback: (v: number | string, i: number) => props.xTickFormatter!(String(v), i) ?? '' }
                : undefined,
        },
        y: {
            display: !props.hideYAxis,
            type: props.yScaleType === 'log' ? 'logarithmic' : 'linear',
            stacked: props.percentStackView ?? false,
            position: 'left',
            ticks: props.yTickFormatter
                ? { callback: (v: number | string) => props.yTickFormatter!(Number(v)) }
                : undefined,
        },
    }

    // Add additional Y-axis entries when multipleYAxes is enabled
    if (props.multipleYAxes) {
        for (const s of props.series) {
            if (s.yAxisId && s.yAxisId !== 'y') {
                scales![s.yAxisId] = {
                    display: true,
                    type: props.yScaleType === 'log' ? 'logarithmic' : 'linear',
                    stacked: props.percentStackView ?? false,
                    position: 'right',
                }
            }
        }
    }

    const plugins: Record<string, unknown> = {}

    if (props.goalLines && props.goalLines.length > 0) {
        const annotations: Record<string, unknown> = {}
        props.goalLines.forEach((g, i) => {
            annotations[`line-${i}`] = {
                type: 'line',
                yMin: g.value,
                yMax: g.value,
                borderColor: g.borderColor,
                label: { content: g.label },
            }
        })
        plugins.annotation = { annotations }
    }

    if (props.showDataLabels) {
        plugins.datalabels = { display: true }
    }

    return {
        type: 'line',
        data: {
            labels: props.labels,
            datasets,
        },
        options: {
            scales,
            ...(Object.keys(plugins).length > 0 ? { plugins } : {}),
            ...(props.showTrendLines ? { showTrendLines: true } : {}),
        },
    }
}

/** Build the same data-attr DOM structure the Chart.js mock produces. */
function buildTestDOM(config: CapturedChartConfig): React.ReactElement {
    const labels = config.data?.labels ?? []
    const datasets = config.data?.datasets ?? []

    return (
        <div data-attr="chart-data" data-type={config.type ?? ''}>
            <div data-attr="chart-labels">
                {labels.map((label, i) => (
                    <span key={i} data-attr={`label-${i}`}>
                        {label}
                    </span>
                ))}
            </div>
            <div data-attr="chart-datasets">
                {datasets.map((ds, i) => (
                    <div
                        key={i}
                        data-attr={`dataset-${i}`}
                        data-label={ds.label ?? ''}
                        data-hidden={String(ds.hidden ?? false)}
                        data-count=""
                        data-compare="false"
                        data-compare-label=""
                        data-status=""
                    >
                        {(ds.data ?? []).map((v, j) => (
                            <span key={j} data-attr={`dataset-${i}-point-${j}`} data-value={String(v)} />
                        ))}
                    </div>
                ))}
            </div>
        </div>
    )
}

export function LineChart(props: LineChartProps): React.ReactElement {
    const capturedRef = useRef(false)

    useEffect(() => {
        const config = propsToCapturedChartConfig(props)
        pushCapturedChart(config, null)
        capturedRef.current = true
    })

    const config = propsToCapturedChartConfig(props)

    return (
        <div data-testid="hog-line-chart" className={props.className}>
            {buildTestDOM(config)}
        </div>
    )
}

// Re-export everything else from lib/hog-charts as stubs/pass-throughs.
// The mock only needs to intercept the LineChart component — types and
// utility functions can be the real implementations since tests may use them.
export type { LineChartProps, Series, GoalLine, TooltipContext, PointClickData }

// Stub types that the real module re-exports
export interface ChartDimensions {
    width: number
    height: number
    plotLeft: number
    plotTop: number
    plotWidth: number
    plotHeight: number
}

export interface ChartMargins {
    top: number
    right: number
    bottom: number
    left: number
}

// Stub out functions that tests shouldn't need
export function createXScale(): unknown {
    return undefined
}
export function createYScale(): unknown {
    return undefined
}
export function createScales(): unknown {
    return undefined
}
export function computePercentStackData(): unknown {
    return undefined
}
export function autoFormatYTick(): string {
    return ''
}
export function findNearestIndex(): number {
    return -1
}
export function buildTooltipContext(): unknown {
    return undefined
}
export function buildPointClickData(): unknown {
    return undefined
}
export function linearRegression(): unknown {
    return undefined
}
export function drawLine(): void {}
export function drawArea(): void {}
export function drawGrid(): void {}
export function drawPoints(): void {}
export function drawHighlightPoint(): void {}

// Overlay stubs — these are React components but won't render in tests
export function AxisLabels(): null {
    return null
}
export function Crosshair(): null {
    return null
}
export function DataLabels(): null {
    return null
}
export function GoalLines(): null {
    return null
}
export function Tooltip(): null {
    return null
}
export function TrendLine(): null {
    return null
}
export function ZoomBrush(): null {
    return null
}
