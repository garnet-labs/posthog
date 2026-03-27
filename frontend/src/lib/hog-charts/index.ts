// Components
export { LineChart } from './components/LineChart'
export type { LineChartProps } from './components/LineChart'

// Chart context (for custom overlay children)
export { useChart } from './core/chart-context'
export type { BaseChartContext, LineChartContext } from './core/chart-context'

// Core types
export type { GoalLine, LineChartConfig, PointClickData, Series, TooltipContext } from './core/types'

// Built-in tooltip (for reference or extension)
export { DefaultTooltip } from './overlays/DefaultTooltip'
