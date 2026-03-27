import React, { useCallback, useMemo } from 'react'

import { drawArea, drawGrid, drawHighlightPoint, drawLine, drawPoints } from '../core/canvas-renderer'
import type { DrawContext } from '../core/canvas-renderer'
import { Chart } from '../core/Chart'
import { computePercentStackData, createScales as createLineScales } from '../core/scales'
import type {
    ChartDimensions,
    ChartDrawArgs,
    ChartScales,
    CreateScalesFn,
    LineChartConfig,
    PointClickData,
    Series,
    TooltipContext,
} from '../core/types'
import { DataLabels } from '../overlays/DataLabels'
import { TrendLine } from '../overlays/TrendLine'

export interface LineChartProps {
    series: Series[]
    labels: string[]
    config?: LineChartConfig
    tooltip?: React.ComponentType<TooltipContext>
    onPointClick?: (data: PointClickData) => void
    onRangeSelect?: (startIndex: number, endIndex: number) => void
    className?: string
    children?: React.ReactNode
}

export function LineChart({
    series,
    labels,
    config,
    tooltip,
    onPointClick,
    onRangeSelect,
    className,
    children,
}: LineChartProps): React.ReactElement {
    const {
        yScaleType = 'linear',
        multipleYAxes = false,
        percentStackView = false,
        showGrid = false,
        showDataLabels = false,
        dataLabelFormatter,
        showTrendLines = false,
        incompleteFromIndex,
        goalLines,
    } = config ?? {}

    const stackedData = useMemo(() => {
        if (!percentStackView) {
            return undefined
        }
        return computePercentStackData(series, labels)
    }, [percentStackView, series, labels])

    // Override y-tick formatter for percent stack view
    const chartConfig = useMemo(() => {
        if (!percentStackView || config?.yTickFormatter) {
            return config
        }
        return {
            ...config,
            yTickFormatter: (v: number) => `${Math.round(v * 100)}%`,
        }
    }, [config, percentStackView])

    const createScales: CreateScalesFn = useCallback(
        (coloredSeries: Series[], scaleLabels: string[], dimensions: ChartDimensions): ChartScales => {
            const scales = createLineScales(coloredSeries, scaleLabels, dimensions, {
                scaleType: yScaleType,
                percentStack: percentStackView,
                multipleYAxes,
            })
            return {
                x: (label: string) => scales.x(label),
                y: (value: number) => scales.y(value),
                yAxes: new Map(Array.from(scales.yAxes.entries()).map(([id, s]) => [id, (v: number) => s(v)])),
                yRaw: scales.y,
            }
        },
        [yScaleType, percentStackView, multipleYAxes]
    )

    const draw = useCallback(
        ({ ctx, dimensions, scales, series: coloredSeries, labels: drawLabels, hoverIndex, theme }: ChartDrawArgs) => {
            const drawCtx: DrawContext = {
                ctx,
                dimensions,
                xScale: scales.x as unknown as d3.ScalePoint<string>,
                yScale: scales.yRaw,
                labels: drawLabels,
            }

            if (showGrid) {
                drawGrid(drawCtx, {
                    gridColor: theme.gridColor,
                    goalLineValues: goalLines?.map((g) => g.value),
                })
            }

            for (const s of coloredSeries) {
                if (s.hidden) {
                    continue
                }

                const yScale =
                    multipleYAxes && s.yAxisId && scales.yAxes.has(s.yAxisId) ? scales.yAxes.get(s.yAxisId)! : scales.y
                const seriesDrawCtx: DrawContext = {
                    ...drawCtx,
                    yScale: yScale as unknown as typeof drawCtx.yScale,
                }
                const yValues = stackedData?.get(s.key)

                if (s.fillArea) {
                    drawArea(seriesDrawCtx, s, yValues, { incompleteFromIndex })
                }
                drawLine(seriesDrawCtx, s, yValues, { incompleteFromIndex })
                drawPoints(seriesDrawCtx, s, yValues)
            }

            if (hoverIndex >= 0) {
                for (const s of coloredSeries) {
                    if (s.hidden) {
                        continue
                    }
                    const data = stackedData?.get(s.key) ?? s.data
                    const x = scales.x(drawLabels[hoverIndex])
                    const yScale =
                        multipleYAxes && s.yAxisId && scales.yAxes.has(s.yAxisId)
                            ? scales.yAxes.get(s.yAxisId)!
                            : scales.y
                    const y = yScale(data[hoverIndex])
                    if (x != null && isFinite(y)) {
                        drawHighlightPoint(ctx, x, y, s.color)
                    }
                }
            }
        },
        [showGrid, goalLines, multipleYAxes, stackedData, incompleteFromIndex]
    )

    return (
        <Chart
            series={series}
            labels={labels}
            config={chartConfig}
            createScales={createScales}
            draw={draw}
            tooltip={tooltip}
            onPointClick={onPointClick}
            onRangeSelect={onRangeSelect}
            className={className}
            stackedData={stackedData}
        >
            {showDataLabels && <DataLabels formatter={dataLabelFormatter} stackedData={stackedData} />}
            {showTrendLines && <TrendLine incompleteFromIndex={incompleteFromIndex} />}
            {children}
        </Chart>
    )
}
