import React from 'react'

import { useChart } from '../core/chart-context'
import { linearRegression } from '../core/interaction'

interface TrendLineProps {
    incompleteFromIndex?: number
}

export function TrendLine({ incompleteFromIndex }: TrendLineProps): React.ReactElement {
    const { scales, dimensions, labels, series } = useChart()

    return (
        <>
            {series.map((s) => {
                if (s.hidden) {
                    return null
                }

                const endIdx = incompleteFromIndex ?? s.data.length
                const regression = linearRegression(s.data, endIdx)
                if (!regression) {
                    return null
                }

                const startX = scales.x(labels[0])
                const endX = scales.x(labels[Math.min(endIdx - 1, labels.length - 1)])
                if (startX == null || endX == null) {
                    return null
                }

                const startY = scales.y(regression.intercept)
                const endY = scales.y(regression.slope * (endIdx - 1) + regression.intercept)

                if (!isFinite(startY) || !isFinite(endY)) {
                    return null
                }

                return (
                    <svg
                        key={`trend-${s.key}`}
                        style={{
                            position: 'absolute',
                            left: 0,
                            top: 0,
                            width: dimensions.width,
                            height: dimensions.height,
                            pointerEvents: 'none',
                        }}
                    >
                        <line
                            x1={startX}
                            y1={startY}
                            x2={endX}
                            y2={endY}
                            stroke={s.color}
                            strokeWidth={1.5}
                            strokeDasharray="4 4"
                            opacity={0.6}
                        />
                    </svg>
                )
            })}
        </>
    )
}
