// Chart context
export { useChart } from './core/chart-context'
export type { BaseChartContext } from './core/chart-context'

// Core types
export type {
    ChartConfig,
    ChartDimensions,
    ChartDrawArgs,
    ChartMargins,
    ChartScales,
    CreateScalesFn,
    GoalLine,
    LineChartConfig,
    PointClickData,
    Series,
    TooltipContext,
} from './core/types'

// Scales
export { autoFormatYTick, computePercentStackData, createScales, createXScale, createYScale } from './core/scales'

// Canvas rendering
export { drawArea, drawGrid, drawHighlightPoint, drawLine, drawPoints } from './core/canvas-renderer'
