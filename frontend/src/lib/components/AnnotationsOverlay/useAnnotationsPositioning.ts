import { useMemo } from 'react'

import { Chart } from 'lib/Chart'

export interface AnnotationsPositioning {
    tickIntervalPx: number
    firstTickLeftPx: number
}

export function useAnnotationsPositioning(
    chart: Chart | undefined,
    chartWidth: number,
    chartHeight: number
): AnnotationsPositioning {
    // Calculate chart content coordinates for annotations overlay positioning.
    // We use ALL data point positions (not just visible tick positions) so that
    // annotation badges appear at their actual date on the x-axis, rather than
    // snapping to the nearest Chart.js tick which can be several weeks away.
    return useMemo<AnnotationsPositioning>(() => {
        // @ts-expect-error - _metasets is not officially exposed
        if (chart && chart._metasets?.[0]?.data?.length > 1) {
            // @ts-expect-error - _metasets is not officially exposed
            const points = chart._metasets[0].data as Point[]
            const pointCount = points.length
            // Fall back to zero for resiliency against temporary chart inconsistencies during loading
            const firstPointLeftPx = points[0]?.x ?? 0
            const lastPointLeftPx = points[pointCount - 1]?.x ?? 0
            return {
                tickIntervalPx: (lastPointLeftPx - firstPointLeftPx) / (pointCount - 1),
                firstTickLeftPx: firstPointLeftPx,
            }
        }
        return {
            tickIntervalPx: 0,
            firstTickLeftPx: 0,
        }
    }, [chart, chartWidth, chartHeight])
}
