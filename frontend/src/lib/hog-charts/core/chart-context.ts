import * as d3 from 'd3'
import { createContext, useContext } from 'react'

import type { ChartDimensions, Series } from './types'

export interface BaseChartContext {
    dimensions: ChartDimensions
    labels: string[]
    series: Series[]
}

export interface LineChartContext extends BaseChartContext {
    xScale: d3.ScalePoint<string>
    yScale: d3.ScaleLinear<number, number> | d3.ScaleLogarithmic<number, number>
}

const ChartContext = createContext<BaseChartContext | null>(null)

export function useChart<T extends BaseChartContext = BaseChartContext>(): T {
    const ctx = useContext(ChartContext)
    if (!ctx) {
        throw new Error('useChart must be used inside a chart component (e.g. <LineChart>)')
    }
    return ctx as T
}

export { ChartContext }
