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

/** Known tooltip host selectors — one per renderer.
 *  hog-charts renders into [data-attr="hog-charts-tooltip-host"],
 *  Chart.js renders into [data-attr="insight-tooltip-wrapper"]. */
const TOOLTIP_HOST_SELECTORS = ['[data-attr="hog-charts-tooltip-host"]', '[data-attr="insight-tooltip-wrapper"]']

function findTooltipHost(): HTMLElement | null {
    for (const selector of TOOLTIP_HOST_SELECTORS) {
        const el = document.querySelector<HTMLElement>(selector)
        if (el && el.children.length > 0) {
            return el
        }
    }
    return null
}

/** Wait for a tooltip to render. Works for both Chart.js and hog-charts.
 *  Call `chart.hover(index)` first, then await this to get the tooltip element. */
export async function waitForTooltip(): Promise<HTMLElement> {
    let found: HTMLElement | null = null
    await waitFor(
        () => {
            const host = findTooltipHost()
            expect(host).not.toBeNull()
            found = host!.firstElementChild as HTMLElement
        },
        { timeout: 2000 }
    )
    return found!
}
