import React from 'react'

import { useChart } from '../core/chart-context'
import type { Series } from '../core/types'

interface DataLabelsProps {
    formatter?: (value: number, seriesIndex: number) => string
    stackedData?: Map<string, number[]>
}

interface LabelPosition {
    x: number
    y: number
    text: string
}

export function DataLabels({ formatter, stackedData }: DataLabelsProps): React.ReactElement {
    const { scales, dimensions, labels, series } = useChart()
    const allLabels: LabelPosition[] = []

    series.forEach((s: Series, si: number) => {
        if (s.hidden) {
            return
        }
        const data = stackedData?.get(s.key) ?? s.data
        for (let i = 0; i < data.length; i++) {
            const x = scales.x(labels[i])
            const y = scales.y(data[i])
            if (x == null || !isFinite(y)) {
                continue
            }
            const text = formatter ? formatter(data[i], si) : String(Math.round(data[i] * 100) / 100)
            allLabels.push({ x, y: y - 12, text })
        }
    })

    // Simple collision detection: skip labels that overlap
    const rendered: LabelPosition[] = []
    const MIN_GAP = 30

    for (const label of allLabels) {
        const overlaps = rendered.some((r) => Math.abs(r.x - label.x) < MIN_GAP && Math.abs(r.y - label.y) < 14)
        if (!overlaps) {
            rendered.push(label)
        }
    }

    return (
        <>
            {rendered.map((label, i) => {
                if (label.x < dimensions.plotLeft || label.x > dimensions.plotLeft + dimensions.plotWidth) {
                    return null
                }
                return (
                    <div
                        key={i}
                        style={{
                            position: 'absolute',
                            left: label.x,
                            top: label.y,
                            transform: 'translateX(-50%)',
                            fontSize: 10,
                            fontWeight: 500,
                            color: 'rgba(0, 0, 0, 0.7)',
                            pointerEvents: 'none',
                            whiteSpace: 'nowrap',
                        }}
                    >
                        {label.text}
                    </div>
                )
            })}
        </>
    )
}
