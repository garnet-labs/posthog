/**
 * Renderer-agnostic store for charts captured by the insight-testing mocks.
 *
 * Both the Chart.js mock (`chartjs-mock.ts`) and the hog-charts mock
 * (`hog-charts-mock.tsx`) push normalized entries into this store. The
 * chart-accessor reads from the merged store so test assertions remain
 * identical across renderers.
 */

export interface NormalizedDataset {
    label: string
    data: number[]
    hidden: boolean
    borderColor: string
    backgroundColor: string
    compare: boolean
    compareLabel: string
    meta?: Record<string, unknown>
}

export interface NormalizedAxis {
    display: boolean
    type: string
    stacked: boolean
    position: string
    tickLabel: (value: number | string) => string
}

export interface NormalizedChart {
    renderer: 'chartjs' | 'hog-charts'
    type: string
    labels: string[]
    datasets: NormalizedDataset[]
    axes: Record<string, NormalizedAxis>
    /** Escape hatch — original config (Chart.js) or props (hog-charts). */
    raw: unknown
    /** Drive hover state from tests. Triggers tooltip rendering at the given data index. */
    hover: (index: number) => void
    /** Pin the tooltip so it stays visible and becomes interactive. */
    pin: () => void
    /** Unpin the tooltip. */
    unpin: () => void
    /** Returns the DOM element hosting the tooltip content. */
    getTooltipHost: () => HTMLElement | null
}

let captured: NormalizedChart[] = []

export function pushCapturedChart(chart: NormalizedChart): void {
    captured.push(chart)
}

export function getAllCapturedCharts(): NormalizedChart[] {
    return captured
}

export function resetAllCapturedCharts(): void {
    captured = []
}
