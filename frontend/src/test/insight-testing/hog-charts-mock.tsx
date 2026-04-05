import React, { useMemo, useRef, useState } from 'react'

// Re-export type-only symbols from the real module. Types erase at runtime, so
// this costs nothing and keeps consumers typing cleanly.
export type {
    ChartConfig,
    ChartDrawArgs,
    ChartScales,
    CreateScalesFn,
    GoalLine,
    LineChartConfig,
    PointClickData,
    ResolveValueFn,
    Series,
    TooltipContext,
} from 'lib/hog-charts/core/types'

import type { ChartTheme } from 'lib/charts/types'
import type {
    LineChartConfig as _LineChartConfig,
    Series as _Series,
    TooltipContext as _TooltipContext,
} from 'lib/hog-charts/core/types'

import { type NormalizedChart, pushCapturedChart } from './captured-charts'

// The mock intentionally does not re-export non-component symbols (useChart,
// DefaultTooltip, BaseChartContext). The current consumers of lib/hog-charts
// under test (TrendsLineChartD3) only use LineChart + types, and those types
// erase at runtime. Add re-exports here if a new consumer lands.

interface CaptureShimProps {
    kind: 'LineChart' | 'Chart'
    series: _Series[]
    labels: string[]
    config?: _LineChartConfig
    theme: ChartTheme
    tooltip?: (ctx: _TooltipContext) => React.ReactNode
    onPointClick?: unknown
    className?: string
    children?: React.ReactNode
}

function buildNormalizedFromProps(
    kind: 'LineChart' | 'Chart',
    series: _Series[],
    labels: string[],
    config: _LineChartConfig | undefined,
    entry: NormalizedChart
): void {
    entry.type = kind === 'LineChart' ? 'line' : 'chart'
    entry.labels = labels
    entry.datasets = series.map((s) => ({
        label: s.label,
        data: s.data,
        hidden: s.hidden ?? false,
        borderColor: s.color,
        backgroundColor: s.fillArea ? s.color : '',
        compare: s.meta?.compare_label != null,
        compareLabel: s.meta?.compare_label != null ? String(s.meta.compare_label) : '',
        meta: s.meta,
    }))
    entry.axes = {
        x: {
            display: true,
            type: 'category',
            stacked: false,
            position: 'bottom',
            tickLabel: (v) => {
                const cb = config?.xTickFormatter
                if (typeof cb === 'function') {
                    const out = cb(String(v), 0)
                    return out == null ? '' : String(out)
                }
                return String(v)
            },
        },
        y: {
            display: true,
            type: config?.yScaleType === 'log' ? 'log' : 'linear',
            stacked: !!config?.percentStackView,
            position: 'left',
            tickLabel: (v) => {
                const cb = config?.yTickFormatter
                return typeof cb === 'function' && typeof v === 'number' ? String(cb(v)) : String(v)
            },
        },
    }
}

function CaptureShim(props: CaptureShimProps): React.ReactElement {
    const { kind, series, labels, config, tooltip, children } = props

    const tooltipHostRef = useRef<HTMLDivElement | null>(null)
    const [hoverIndex, setHoverIndex] = useState<number>(-1)
    const [isPinned, setIsPinned] = useState<boolean>(false)

    // Mutable normalized entry — the same reference is returned for every
    // accessor call, so late data updates (hover-driven tooltip rebuilds)
    // are visible without re-pushing to the store.
    const entryRef = useRef<NormalizedChart | null>(null)
    if (entryRef.current === null) {
        const entry: NormalizedChart = {
            renderer: 'hog-charts',
            type: kind === 'LineChart' ? 'line' : 'chart',
            labels: [],
            datasets: [],
            axes: {} as NormalizedChart['axes'],
            raw: props,
            hover: (i: number) => setHoverIndex(i),
            pin: () => setIsPinned(true),
            unpin: () => setIsPinned(false),
            getTooltipHost: () => tooltipHostRef.current,
        }
        entryRef.current = entry
        pushCapturedChart(entry)
    }
    // Keep the normalized projection current on every render so tests that
    // read the accessor after a props change see fresh data.
    buildNormalizedFromProps(kind, series, labels, config, entryRef.current!)
    entryRef.current!.raw = props

    const visibleSeries = useMemo(() => series.filter((s) => !s.hidden), [series])

    const tooltipNode = useMemo(() => {
        if (!tooltip || hoverIndex < 0 || hoverIndex >= labels.length) {
            return null
        }
        const ctx: _TooltipContext = {
            dataIndex: hoverIndex,
            label: labels[hoverIndex] ?? '',
            seriesData: visibleSeries.map((s) => ({ series: s, value: s.data[hoverIndex], color: s.color })),
            position: { x: 0, y: 0 },
            canvasBounds: {
                x: 0,
                y: 0,
                width: 800,
                height: 400,
                top: 0,
                left: 0,
                bottom: 400,
                right: 800,
                toJSON: () => ({}),
            } as DOMRect,
            isPinned,
            onUnpin: isPinned ? () => setIsPinned(false) : undefined,
        }
        return tooltip(ctx)
    }, [tooltip, hoverIndex, isPinned, labels, visibleSeries])

    return (
        <div data-attr="hog-charts-mock" data-renderer="hog-charts" data-kind={kind}>
            <div data-attr="chart-data" data-type={kind === 'LineChart' ? 'line' : 'chart'}>
                <div data-attr="chart-labels">
                    {labels.map((l, i) => (
                        <span key={i} data-attr={`label-${i}`}>
                            {l}
                        </span>
                    ))}
                </div>
                <div data-attr="chart-datasets">
                    {series.map((s, i) => (
                        <div
                            key={i}
                            data-attr={`dataset-${i}`}
                            data-label={s.label}
                            data-hidden={String(s.hidden ?? false)}
                        >
                            {s.data.map((v, j) => (
                                <span key={j} data-attr={`dataset-${i}-point-${j}`} data-value={String(v)} />
                            ))}
                        </div>
                    ))}
                </div>
            </div>
            <div ref={tooltipHostRef} data-attr="hog-charts-tooltip-host">
                {tooltipNode}
            </div>
            {children}
        </div>
    )
}

export function LineChart(props: Omit<CaptureShimProps, 'kind'>): React.ReactElement {
    return <CaptureShim kind="LineChart" {...props} />
}

export function Chart(props: Omit<CaptureShimProps, 'kind'>): React.ReactElement {
    return <CaptureShim kind="Chart" {...props} />
}

export type { LineChartProps } from 'lib/hog-charts/charts/LineChart'
export type { ChartProps } from 'lib/hog-charts/core/Chart'
