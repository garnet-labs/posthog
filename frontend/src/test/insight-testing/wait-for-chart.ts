import { waitFor } from '@testing-library/react'

import { getAllCapturedCharts } from './captured-charts'
import { type Chart, getChart } from './chart-accessor'

/** Wait for a new chart to render. On each call, waits for a chart that
 *  didn't exist when waitForChart was invoked, so back-to-back calls
 *  after interactions always return fresh data. */
export async function waitForChart(): Promise<Chart> {
    const countAtCall = getAllCapturedCharts().length
    let chart: Chart
    await waitFor(
        () => {
            expect(getAllCapturedCharts().length).toBeGreaterThan(countAtCall)
            chart = getChart()
            expect(chart.seriesCount).toBeGreaterThan(0)
        },
        { timeout: 2000 }
    )
    return chart!
}

/** Wait for a hog-charts tooltip to render inside the tooltip host for the
 *  given chart. Returns the first child element (the rendered tooltip). */
export async function waitForTooltip(chart: Chart): Promise<HTMLElement> {
    let found: HTMLElement | null = null
    await waitFor(
        () => {
            const host = chart.tooltipHost()
            expect(host).not.toBeNull()
            expect(host!.children.length).toBeGreaterThan(0)
            found = host!.firstElementChild as HTMLElement
        },
        { timeout: 2000 }
    )
    return found!
}
