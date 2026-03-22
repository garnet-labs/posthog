import {
    type CapturedChartConfig,
    getCapturedCharts,
    pushCapturedChart,
    resetCapturedCharts as resetSharedCapture,
} from './captured-charts'

// Re-export types so existing consumers (chart-accessor, etc.) keep working
export type ChartDataset = NonNullable<NonNullable<CapturedChartConfig['data']>['datasets']>[number]
export type ChartScaleConfig = NonNullable<NonNullable<CapturedChartConfig['options']>['scales']>[string]
export type ChartConfig = CapturedChartConfig

export function resetCapturedCharts(): void {
    resetSharedCapture()
    MockChart._instances = []
}

/** Returns all captured chart snapshots from both Chart.js and HogLineChart mocks. */
export function getCapturedChartConfigs(): ReturnType<typeof getCapturedCharts> {
    return getCapturedCharts()
}

const defaults: Record<string, unknown> = {
    animation: false,
    plugins: { legend: { labels: { generateLabels: () => [] } } },
}

class MockChart {
    static _instances: MockChart[] = []
    static defaults = defaults
    config: ChartConfig
    canvas: HTMLCanvasElement
    data: ChartConfig['data']

    constructor(canvas: HTMLCanvasElement, config: ChartConfig) {
        this.canvas = canvas
        this.config = config
        this.data = config.data
        MockChart._instances.push(this)
        pushCapturedChart(config, canvas)

        const container = canvas.parentElement
        if (container) {
            renderChartDOM(container, config)
        }
    }

    static getChart(_canvas: HTMLCanvasElement): MockChart | undefined {
        return MockChart._instances.find((i) => i.canvas === _canvas)
    }

    static register(): void {}
    destroy(): void {
        MockChart._instances = MockChart._instances.filter((i) => i !== this)
    }
    update(): void {}
    resize(): void {}
    reset(): void {}
    stop(): void {}
    toBase64Image(): string {
        return ''
    }
    getElementsAtEventForMode(): unknown[] {
        return []
    }
}

function buildLabelsDOM(labels: string[]): HTMLDivElement {
    const el = document.createElement('div')
    el.setAttribute('data-attr', 'chart-labels')
    for (const [i, label] of labels.entries()) {
        const span = document.createElement('span')
        span.setAttribute('data-attr', `label-${i}`)
        span.textContent = String(label)
        el.appendChild(span)
    }
    return el
}

function buildDatasetDOM(ds: ChartDataset, index: number): HTMLDivElement {
    const el = document.createElement('div')
    el.setAttribute('data-attr', `dataset-${index}`)
    el.setAttribute('data-label', ds.label ?? '')
    el.setAttribute('data-hidden', String(ds.hidden ?? false))
    el.setAttribute('data-count', String(ds.count ?? ''))
    el.setAttribute('data-compare', String(ds.compare ?? false))
    el.setAttribute('data-compare-label', ds.compare_label ?? '')
    el.setAttribute('data-status', ds.status ?? '')
    for (const [j, v] of (ds.data ?? []).entries()) {
        const point = document.createElement('span')
        point.setAttribute('data-attr', `dataset-${index}-point-${j}`)
        point.setAttribute('data-value', String(v))
        el.appendChild(point)
    }
    return el
}

function renderChartDOM(container: HTMLElement, config: ChartConfig): void {
    const wrapper = document.createElement('div')
    wrapper.setAttribute('data-attr', 'chart-data')
    wrapper.setAttribute('data-type', config.type ?? '')

    wrapper.appendChild(buildLabelsDOM(config.data?.labels ?? []))

    const datasetsEl = document.createElement('div')
    datasetsEl.setAttribute('data-attr', 'chart-datasets')
    for (const [i, ds] of (config.data?.datasets ?? []).entries()) {
        datasetsEl.appendChild(buildDatasetDOM(ds, i))
    }
    wrapper.appendChild(datasetsEl)

    container.appendChild(wrapper)
}

export const Chart = MockChart
export { defaults }
export const registerables: unknown[] = []
export const Tooltip = { positioners: {} as Record<string, unknown> }
