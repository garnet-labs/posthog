import {
    type NormalizedAxis,
    type NormalizedChart,
    type NormalizedDataset,
    getAllCapturedCharts,
    pushCapturedChart,
    resetAllCapturedCharts,
} from './captured-charts'

export interface ChartDataset {
    label?: string
    data?: number[]
    hidden?: boolean
    count?: number
    compare?: boolean
    compare_label?: string
    status?: string
    borderColor?: string
    backgroundColor?: string
    yAxisID?: string
    [key: string]: unknown
}

export interface ChartScaleConfig {
    display?: boolean
    type?: string
    stacked?: boolean
    position?: string
    ticks?: { callback?: (value: number | string, index: number, values: unknown[]) => string }
}

export interface ChartConfig {
    type?: string
    data?: { labels?: string[]; datasets?: ChartDataset[] }
    options?: {
        scales?: Record<string, ChartScaleConfig>
        plugins?: { tooltip?: { external?: (ctx: { chart: unknown; tooltip: unknown }) => void } }
        [key: string]: unknown
    }
}

export function resetCapturedCharts(): void {
    resetAllCapturedCharts()
    MockChart._instances = []
}

/** @deprecated — use `getAllCapturedCharts` from `captured-charts`. Kept as a thin
 *  compat shim that filters to Chart.js entries and exposes the legacy `{config, canvas}`
 *  shape. Only the `config` field is actually populated (canvas is unused by callers). */
export function getCapturedChartConfigs(): { config: ChartConfig; canvas: HTMLCanvasElement | null }[] {
    return getAllCapturedCharts()
        .filter((c) => c.renderer === 'chartjs')
        .map((c) => ({ config: c.raw as ChartConfig, canvas: null }))
}

const defaults: Record<string, unknown> = {
    animation: false,
    plugins: { legend: { labels: { generateLabels: () => [] } } },
}

function toNormalizedDataset(ds: ChartDataset): NormalizedDataset {
    return {
        label: ds.label ?? '',
        data: ds.data ?? [],
        hidden: ds.hidden ?? false,
        borderColor: ds.borderColor ?? '',
        backgroundColor: ds.backgroundColor ?? '',
        compare: ds.compare ?? false,
        compareLabel: ds.compare_label ?? '',
    }
}

function toNormalizedAxis(scale: ChartScaleConfig | undefined): NormalizedAxis {
    return {
        display: scale?.display ?? true,
        type: scale?.type ?? 'linear',
        stacked: scale?.stacked ?? false,
        position: scale?.position ?? 'left',
        tickLabel: (value) => {
            const cb = scale?.ticks?.callback
            return typeof cb === 'function' ? String(cb(value, 0, [])) : String(value)
        },
    }
}

function toNormalizedChart(config: ChartConfig, mock: MockChart): NormalizedChart {
    const axes: Record<string, NormalizedAxis> = {}
    const scales = config.options?.scales ?? {}
    for (const [key, scale] of Object.entries(scales)) {
        axes[key] = toNormalizedAxis(scale)
    }
    if (!axes.x) {
        axes.x = toNormalizedAxis(undefined)
    }
    if (!axes.y) {
        axes.y = toNormalizedAxis(undefined)
    }
    return {
        renderer: 'chartjs',
        type: config.type ?? '',
        labels: config.data?.labels ?? [],
        datasets: (config.data?.datasets ?? []).map(toNormalizedDataset),
        axes,
        raw: config,
        hover: (index) => mock.triggerTooltip(index),
        pin: () => {},
        unpin: () => {},
        getTooltipHost: () => mock.getTooltipHost(),
    }
}

class MockChart {
    static _instances: MockChart[] = []
    static defaults = defaults
    config: ChartConfig
    canvas: HTMLCanvasElement
    data: ChartConfig['data']
    private externalHandler: ((ctx: { chart: unknown; tooltip: unknown }) => void) | undefined
    options: ChartConfig['options']
    tooltip: { body?: unknown[] }

    constructor(canvas: HTMLCanvasElement, config: ChartConfig) {
        this.canvas = canvas
        this.config = config
        this.data = config.data
        this.options = config.options
        this.tooltip = {}
        this.externalHandler = config.options?.plugins?.tooltip?.external
        MockChart._instances.push(this)
        pushCapturedChart(toNormalizedChart(config, this))

        const container = canvas.parentElement
        if (container) {
            renderChartDOM(container, config)
        }
    }

    /** Call the real external tooltip handler from LineGraph with fabricated data.
     *  This triggers real InsightTooltip rendering into the tooltip wrapper div
     *  that useInsightTooltip creates during component mount. */
    triggerTooltip(index: number): void {
        if (!this.externalHandler) {
            return
        }
        const datasets = this.config.data?.datasets ?? []
        const tooltipModel = {
            opacity: index >= 0 ? 1 : 0,
            dataPoints:
                index >= 0
                    ? datasets
                          .filter((ds) => !ds.hidden)
                          .map((ds, dsIdx) => ({
                              dataIndex: index,
                              datasetIndex: dsIdx,
                              dataset: ds,
                          }))
                    : [],
            body: index >= 0 ? [['data']] : [],
            yAlign: 'no-transform',
            caretX: 100,
            caretY: 100,
        }
        this.tooltip = { body: tooltipModel.body }
        this.externalHandler({ chart: this, tooltip: tooltipModel })
    }

    /** Find the tooltip wrapper div that useInsightTooltip appended to the body. */
    getTooltipHost(): HTMLElement | null {
        return document.querySelector('[data-attr="insight-tooltip-wrapper"]')
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
    isZoomingOrPanning(): boolean {
        return false
    }
    setActiveElements(): void {}
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
