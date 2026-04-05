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
    /** hog-charts Series.meta, undefined on chartjs */
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
    /** hog-charts only: drive hover state from tests. Throws on chartjs entries. */
    hover?: (index: number) => void
    /** hog-charts only: pin the fabricated tooltip context. */
    pin?: () => void
    /** hog-charts only: unpin. */
    unpin?: () => void
    /** hog-charts only: the DOM host where the tooltip render prop is rendered. */
    getTooltipHost?: () => HTMLElement | null
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
