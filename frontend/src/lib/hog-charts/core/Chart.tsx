import React, { useMemo, useEffect } from 'react'

import { buildTheme } from 'lib/charts/utils/theme'
import { getSeriesColor } from 'lib/colors'

import { AxisLabels, SecondaryYAxis } from '../overlays/AxisLabels'
import { Crosshair } from '../overlays/Crosshair'
import { DefaultTooltip } from '../overlays/DefaultTooltip'
import { GoalLines } from '../overlays/GoalLines'
import { Tooltip } from '../overlays/Tooltip'
import { ZoomBrush } from '../overlays/ZoomBrush'
import { ChartContext } from './chart-context'
import { autoFormatYTick } from './scales'
import type {
    ChartConfig,
    ChartDrawArgs,
    ChartMargins,
    ChartScales,
    CreateScalesFn,
    PointClickData,
    Series,
    TooltipContext,
} from './types'
import { useChartCanvas } from './use-chart-canvas'
import { useChartInteraction } from './use-chart-interaction'

function OverlayLayer({ children }: { children: React.ReactNode }): React.ReactElement {
    return (
        <div
            style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none',
            }}
        >
            {children}
        </div>
    )
}

export interface ChartProps {
    series: Series[]
    labels: string[]
    config?: ChartConfig
    createScales: CreateScalesFn
    draw: (args: ChartDrawArgs) => void
    tooltip?: React.ComponentType<TooltipContext>
    onPointClick?: (data: PointClickData) => void
    onRangeSelect?: (startIndex: number, endIndex: number) => void
    className?: string
    children?: React.ReactNode
    stackedData?: Map<string, number[]>
}

const DEFAULT_MARGINS: ChartMargins = { top: 16, right: 16, bottom: 32, left: 48 }

export function Chart({
    series,
    labels,
    config,
    createScales: createScalesFn,
    draw,
    tooltip: TooltipComponent = DefaultTooltip,
    onPointClick,
    onRangeSelect,
    className,
    children,
    stackedData,
}: ChartProps): React.ReactElement {
    const {
        multipleYAxes = false,
        xTickFormatter,
        yTickFormatter,
        hideXAxis = false,
        hideYAxis = false,
        showTooltip = true,
        showCrosshair = false,
        goalLines,
    } = config ?? {}

    const theme = useMemo(() => buildTheme(), [])

    const margins = useMemo<ChartMargins>(() => {
        const m = { ...DEFAULT_MARGINS }
        if (hideXAxis) {
            m.bottom = 8
        }
        if (hideYAxis) {
            m.left = 8
        }
        if (multipleYAxes) {
            m.right = 48
        }
        return m
    }, [hideXAxis, hideYAxis, multipleYAxes])

    const { canvasRef, wrapperRef, dimensions, ctx } = useChartCanvas({ margins })

    const coloredSeries = useMemo(
        () =>
            series.map((s, i) => ({
                ...s,
                color: s.color || getSeriesColor(i),
            })),
        [series]
    )

    const scales = useMemo<ChartScales | null>(() => {
        if (!dimensions) {
            return null
        }
        return createScalesFn(coloredSeries, labels, dimensions)
    }, [coloredSeries, labels, dimensions, createScalesFn])

    const resolvedYFormatter = useMemo(() => {
        if (yTickFormatter) {
            return yTickFormatter
        }
        const domain = scales?.yRaw.domain() ?? [0, 1]
        const domainMax = Math.abs(domain[1])
        return (v: number) => autoFormatYTick(v, domainMax)
    }, [yTickFormatter, scales])

    const { hoverIndex, tooltipCtx, brushStart, brushCurrent, isDragging, handlers } = useChartInteraction({
        scales,
        dimensions,
        labels,
        series: coloredSeries,
        canvasRef,
        showTooltip,
        onPointClick,
        onRangeSelect,
        stackedData,
    })

    // Canvas rendering
    useEffect(() => {
        if (!ctx || !dimensions || !scales) {
            return
        }

        const dpr = window.devicePixelRatio || 1
        ctx.save()
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        ctx.clearRect(0, 0, dimensions.width, dimensions.height)

        draw({
            ctx,
            dimensions,
            scales,
            series: coloredSeries,
            labels,
            hoverIndex,
            theme,
        })

        ctx.restore()
    }, [ctx, dimensions, scales, coloredSeries, labels, theme, hoverIndex, draw])

    const secondaryAxes = useMemo(
        () => Array.from(scales?.yAxes.entries() ?? []).filter(([id]) => id !== 'y'),
        [scales]
    )

    const cursorStyle = hoverIndex >= 0 && onPointClick ? 'pointer' : 'default'

    const contextValue = useMemo(() => {
        if (!scales || !dimensions) {
            return null
        }
        return {
            scales,
            dimensions,
            labels,
            series: coloredSeries,
            hoverIndex,
        }
    }, [scales, dimensions, labels, coloredSeries, hoverIndex])

    return (
        <ChartContext.Provider value={contextValue}>
            <div
                ref={wrapperRef as React.RefObject<HTMLDivElement>}
                className={className}
                style={{ position: 'relative', width: '100%', flex: 1, minHeight: 0, cursor: cursorStyle }}
                onMouseMove={handlers.onMouseMove}
                onMouseLeave={handlers.onMouseLeave}
                onMouseDown={handlers.onMouseDown}
                onMouseUp={handlers.onMouseUp}
                onClick={handlers.onClick}
            >
                <canvas
                    ref={canvasRef as React.RefObject<HTMLCanvasElement>}
                    style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        cursor: cursorStyle,
                    }}
                />

                {dimensions && scales && (
                    <OverlayLayer>
                        <AxisLabels
                            xTickFormatter={xTickFormatter}
                            yTickFormatter={resolvedYFormatter}
                            hideXAxis={hideXAxis}
                            hideYAxis={hideYAxis}
                            axisColor={theme.axisColor}
                        />

                        {multipleYAxes &&
                            secondaryAxes.map(([axisId, yScaleFn], i) => (
                                <SecondaryYAxis
                                    key={axisId}
                                    axisId={axisId}
                                    yScale={yScaleFn}
                                    yTickFormatter={resolvedYFormatter}
                                    axisColor={theme.axisColor}
                                    side={i % 2 === 0 ? 'right' : 'left'}
                                />
                            ))}

                        {showCrosshair && !isDragging.current && <Crosshair color={theme.crosshairColor} />}

                        {goalLines && goalLines.length > 0 && <GoalLines goalLines={goalLines} />}

                        {brushStart && brushCurrent != null && (
                            <ZoomBrush startX={brushStart.x} currentX={brushCurrent} dimensions={dimensions} />
                        )}

                        {tooltipCtx && showTooltip && !isDragging.current && (
                            <Tooltip context={tooltipCtx} component={TooltipComponent} />
                        )}

                        {children}
                    </OverlayLayer>
                )}
            </div>
        </ChartContext.Provider>
    )
}
