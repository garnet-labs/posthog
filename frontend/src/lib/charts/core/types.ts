import type * as d3 from 'd3'

export type { AxisFormat, ChartTheme } from '../types'

export interface Series {
    key: string
    label: string
    /** Must be the same length as the labels array. */
    data: number[]
    color: string
    /** Only used when `multipleYAxes` is enabled. */
    yAxisId?: string
    fillArea?: boolean
    /** 0–1, defaults to 0.5. */
    fillOpacity?: number
    /** e.g. [10, 10] for dashed. */
    dashPattern?: number[]
    hidden?: boolean
    /** 0 = no dots. */
    pointRadius?: number
}

export interface GoalLine {
    value: number
    label?: string
    borderColor?: string
    position?: 'start' | 'end'
}

export interface PointClickData {
    seriesIndex: number
    dataIndex: number
    series: Series
    value: number
    label: string
    crossSeriesData: { series: Series; value: number }[]
}

export interface TooltipContext {
    dataIndex: number
    label: string
    seriesData: { series: Series; value: number; color: string }[]
    /** Pixel position relative to the chart container. */
    position: { x: number; y: number }
    canvasBounds: DOMRect
}

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

export interface ChartConfig {
    /** Defaults to 'linear'. 'log' clamps minimum to 1e-10. */
    yScaleType?: 'linear' | 'log'
    multipleYAxes?: boolean
    /** Return null to skip a tick. */
    xTickFormatter?: (value: string, index: number) => string | null
    yTickFormatter?: (value: number) => string
    hideXAxis?: boolean
    hideYAxis?: boolean
    showGrid?: boolean
    /** Defaults to true. */
    showTooltip?: boolean
    showCrosshair?: boolean
    goalLines?: GoalLine[]
}

export interface LineChartConfig extends ChartConfig {
    percentStackView?: boolean
    showDataLabels?: boolean
    dataLabelFormatter?: (value: number, seriesIndex: number) => string
    showTrendLines?: boolean
    /** Data from this index onward renders as dashed/hatched. */
    incompleteFromIndex?: number
}

export interface ChartDrawArgs {
    /** DPR already applied, save/restore handled by Chart. */
    ctx: CanvasRenderingContext2D
    dimensions: ChartDimensions
    scales: ChartScales
    /** Series with fallback colors already applied. */
    series: Series[]
    labels: string[]
    /** -1 when nothing hovered. */
    hoverIndex: number
    theme: import('lib/charts/types').ChartTheme
}

export type CreateScalesFn = (series: Series[], labels: string[], dimensions: ChartDimensions) => ChartScales

export interface ChartScales {
    x: (label: string) => number | undefined
    y: (value: number) => number
    yAxes: Map<string, (value: number) => number>
    /** Underlying d3 scale, needed for tick generation. */
    yRaw: d3.ScaleLinear<number, number> | d3.ScaleLogarithmic<number, number>
}
