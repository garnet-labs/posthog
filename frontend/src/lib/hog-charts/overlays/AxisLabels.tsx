import * as d3 from 'd3'
import React from 'react'

import type { ChartDimensions } from '../core/types'

interface AxisLabelsProps {
    dimensions: ChartDimensions
    xScale: d3.ScalePoint<string>
    yScale: d3.ScaleLinear<number, number> | d3.ScaleLogarithmic<number, number>
    labels: string[]
    xTickFormatter?: (value: string, index: number) => string
    yTickFormatter?: (value: number) => string
    hideXAxis?: boolean
    hideYAxis?: boolean
    axisColor?: string
    /** Side for this Y axis ('left' or 'right') */
    yAxisSide?: 'left' | 'right'
}

export function AxisLabels({
    dimensions,
    xScale,
    yScale,
    labels,
    xTickFormatter,
    yTickFormatter,
    hideXAxis,
    hideYAxis,
    axisColor = 'rgba(0, 0, 0, 0.5)',
    yAxisSide = 'left',
}: AxisLabelsProps): React.ReactElement | null {
    const yTicks = (yScale as d3.ScaleLinear<number, number>).ticks?.() ?? []

    // Thin out X labels if they'd overlap (estimate ~60px per label)
    const maxXLabels = Math.max(1, Math.floor(dimensions.plotWidth / 60))
    const xStep = Math.max(1, Math.ceil(labels.length / maxXLabels))

    return (
        <>
            {/* Y-axis labels */}
            {!hideYAxis &&
                yTicks.map((tick) => {
                    const y = yScale(tick)
                    if (!isFinite(y)) {
                        return null
                    }
                    const label = yTickFormatter ? yTickFormatter(tick) : String(tick)
                    const style: React.CSSProperties =
                        yAxisSide === 'right'
                            ? {
                                  position: 'absolute',
                                  left: dimensions.plotLeft + dimensions.plotWidth + 8,
                                  top: y,
                                  transform: 'translateY(-50%)',
                                  fontSize: 11,
                                  color: axisColor,
                                  pointerEvents: 'none',
                                  whiteSpace: 'nowrap',
                              }
                            : {
                                  position: 'absolute',
                                  right: dimensions.width - dimensions.plotLeft + 8,
                                  top: y,
                                  transform: 'translateY(-50%)',
                                  fontSize: 11,
                                  color: axisColor,
                                  pointerEvents: 'none',
                                  whiteSpace: 'nowrap',
                              }
                    return (
                        <div key={`y-${tick}`} style={style}>
                            {label}
                        </div>
                    )
                })}

            {/* X-axis labels */}
            {!hideXAxis &&
                labels.map((label, i) => {
                    if (i % xStep !== 0) {
                        return null
                    }
                    const x = xScale(label)
                    if (x == null) {
                        return null
                    }
                    const text = xTickFormatter ? xTickFormatter(label, i) : label
                    if (text === null) {
                        return null
                    }
                    return (
                        <div
                            key={`x-${i}`}
                            style={{
                                position: 'absolute',
                                left: x,
                                top: dimensions.plotTop + dimensions.plotHeight + 8,
                                transform: 'translateX(-50%)',
                                fontSize: 11,
                                color: axisColor,
                                pointerEvents: 'none',
                                whiteSpace: 'nowrap',
                            }}
                        >
                            {text}
                        </div>
                    )
                })}
        </>
    )
}
