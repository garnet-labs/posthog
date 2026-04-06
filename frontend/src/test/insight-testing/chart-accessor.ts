import {
    type NormalizedAxis,
    type NormalizedChart,
    type NormalizedDataset,
    getAllCapturedCharts,
} from './captured-charts'
import type { ChartConfig } from './chartjs-mock'

interface Series {
    label: string
    data: number[]
    at(index: number): number
    hidden: boolean
    compare: boolean
    compareLabel: string
    borderColor: string
    backgroundColor: string
    meta?: Record<string, unknown>
}

function makeSeries(ds: NormalizedDataset): Series {
    const data = ds.data
    return {
        label: ds.label,
        data,
        at(index: number): number {
            if (index < 0 || index >= data.length) {
                throw new Error(`Point index ${index} out of range (series "${ds.label}" has ${data.length} points)`)
            }
            return data[index]
        },
        hidden: ds.hidden,
        compare: ds.compare,
        compareLabel: ds.compareLabel,
        borderColor: ds.borderColor,
        backgroundColor: ds.backgroundColor,
        meta: ds.meta,
    }
}

interface Axis {
    display: boolean
    type: string
    stacked: boolean
    position: string
    tickLabel: (value: number | string) => string
}

interface Axes {
    [key: string]: Axis
    x: Axis
    y: Axis
}

function makeAxes(axes: Record<string, NormalizedAxis>): Axes {
    const fallback: NormalizedAxis = {
        display: true,
        type: 'linear',
        stacked: false,
        position: 'left',
        tickLabel: (v) => String(v),
    }
    return new Proxy({ x: axes.x ?? fallback, y: axes.y ?? fallback } as Axes, {
        get(target, prop) {
            if (typeof prop === 'string' && !(prop in target)) {
                return axes[prop] ?? fallback
            }
            return target[prop as keyof typeof target]
        },
    }) as Axes
}

export interface Chart {
    renderer: 'chartjs' | 'hog-charts'
    series(nameOrIndex: string | number): Series
    seriesCount: number
    seriesNames: string[]
    value(series: string | number, pointIndexOrLabel: number | string): number
    labels: string[]
    label(index: number): string
    type: string
    axes: Axes
    raw: unknown
    /** Chart.js config — only populated for Chart.js charts. Use `raw` for renderer-agnostic access. */
    config: ChartConfig
    /** hog-charts only: move the hover index, triggering a tooltip re-render. */
    hover(index: number): void
    /** hog-charts only: pin the current tooltip. */
    pin(): void
    /** hog-charts only: unpin. */
    unpin(): void
    /** hog-charts only: DOM host containing the currently rendered tooltip. */
    tooltipHost(): HTMLElement | null
}

function resolveChart(index: number): NormalizedChart {
    const charts = getAllCapturedCharts()
    if (charts.length === 0) {
        throw new Error('No charts captured')
    }
    const resolved = index < 0 ? charts.length + index : index
    if (resolved < 0 || resolved >= charts.length) {
        throw new Error(`No chart at index ${resolved} (${charts.length} captured)`)
    }
    return charts[resolved]
}

function quotedSeriesNames(allSeries: Series[]): string[] {
    return allSeries.map((s) => `"${s.label}"`)
}

function findSeriesByName(allSeries: Series[], name: string): Series {
    const match = allSeries.find((s) => s.label === name)
    if (!match) {
        throw new Error(`No series "${name}". Available: ${quotedSeriesNames(allSeries).join(', ')}`)
    }
    return match
}

function findSeriesByIndex(allSeries: Series[], index: number): Series {
    if (index < 0 || index >= allSeries.length) {
        throw new Error(
            `Series index ${index} out of range (${allSeries.length} series: ${quotedSeriesNames(allSeries).join(', ')})`
        )
    }
    return allSeries[index]
}

function findSeries(allSeries: Series[], nameOrIndex: string | number): Series {
    return typeof nameOrIndex === 'number'
        ? findSeriesByIndex(allSeries, nameOrIndex)
        : findSeriesByName(allSeries, nameOrIndex)
}

function resolvePointIndex(labels: string[], pointIndexOrLabel: number | string): number {
    if (typeof pointIndexOrLabel === 'number') {
        return pointIndexOrLabel
    }
    const i = labels.indexOf(pointIndexOrLabel)
    if (i < 0) {
        throw new Error(`Label "${pointIndexOrLabel}" not found. Available: ${labels.map((l) => `"${l}"`).join(', ')}`)
    }
    return i
}

function labelAtIndex(labels: string[], index: number): string {
    if (index < 0 || index >= labels.length) {
        throw new Error(`Label index ${index} out of range (${labels.length} labels)`)
    }
    return labels[index]
}

function notSupported(field: string, renderer: string): never {
    throw new Error(`${field} is only supported on hog-charts entries (got renderer: ${renderer})`)
}

export function getChart(index = -1): Chart {
    const normalized = resolveChart(index)
    const allSeries = normalized.datasets.map(makeSeries)
    const chartLabels = normalized.labels

    return {
        renderer: normalized.renderer,
        series: (nameOrIndex) => findSeries(allSeries, nameOrIndex),
        seriesCount: allSeries.length,
        seriesNames: allSeries.map((s) => s.label),
        value: (s, p) => findSeries(allSeries, s).at(resolvePointIndex(chartLabels, p)),
        labels: chartLabels,
        label: (i) => labelAtIndex(chartLabels, i),
        type: normalized.type,
        axes: makeAxes(normalized.axes),
        raw: normalized.raw,
        config: normalized.renderer === 'chartjs' ? (normalized.raw as ChartConfig) : ({} as ChartConfig),
        hover: (i) => (normalized.hover ? normalized.hover(i) : notSupported('hover()', normalized.renderer)),
        pin: () => (normalized.pin ? normalized.pin() : notSupported('pin()', normalized.renderer)),
        unpin: () => (normalized.unpin ? normalized.unpin() : notSupported('unpin()', normalized.renderer)),
        tooltipHost: () =>
            normalized.getTooltipHost
                ? normalized.getTooltipHost()
                : notSupported('tooltipHost()', normalized.renderer),
    }
}
