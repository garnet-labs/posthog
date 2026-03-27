import React, { useCallback, useRef, useState } from 'react'

import { buildPointClickData, buildTooltipContext, findNearestIndex, isInPlotArea } from './interaction'
import type { ChartDimensions, ChartScales, PointClickData, Series, TooltipContext } from './types'

interface UseChartInteractionOptions {
    scales: ChartScales | null
    dimensions: ChartDimensions | null
    labels: string[]
    series: Series[]
    canvasRef: React.RefObject<HTMLCanvasElement | null>
    showTooltip: boolean
    onPointClick?: (data: PointClickData) => void
    onRangeSelect?: (startIndex: number, endIndex: number) => void
    stackedData?: Map<string, number[]>
}

interface UseChartInteractionResult {
    hoverIndex: number
    tooltipCtx: TooltipContext | null
    brushStart: { x: number; index: number } | null
    brushCurrent: number | null
    isDragging: React.RefObject<boolean>
    handlers: {
        onMouseMove: (e: React.MouseEvent<HTMLDivElement>) => void
        onMouseLeave: () => void
        onMouseDown: (e: React.MouseEvent<HTMLDivElement>) => void
        onMouseUp: (e: React.MouseEvent<HTMLDivElement>) => void
        onClick: () => void
    }
}

export function useChartInteraction({
    scales,
    dimensions,
    labels,
    series,
    canvasRef,
    showTooltip,
    onPointClick,
    onRangeSelect,
    stackedData,
}: UseChartInteractionOptions): UseChartInteractionResult {
    const [hoverIndex, setHoverIndex] = useState<number>(-1)
    const [tooltipCtx, setTooltipCtx] = useState<TooltipContext | null>(null)
    const [brushStart, setBrushStart] = useState<{ x: number; index: number } | null>(null)
    const [brushCurrent, setBrushCurrent] = useState<number | null>(null)
    const isDragging = useRef(false)

    const onMouseMove = useCallback(
        (e: React.MouseEvent<HTMLDivElement>) => {
            if (!scales || !dimensions) {
                return
            }

            const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
            const mouseX = e.clientX - rect.left
            const mouseY = e.clientY - rect.top

            if (isDragging.current) {
                setBrushCurrent(mouseX)
                return
            }

            if (!isInPlotArea(mouseX, mouseY, dimensions)) {
                setHoverIndex(-1)
                setTooltipCtx(null)
                return
            }

            const index = findNearestIndex(mouseX, labels, scales.x)
            setHoverIndex(index)

            if (index >= 0 && showTooltip) {
                const canvasBounds = canvasRef.current?.getBoundingClientRect() ?? new DOMRect()
                const newTooltipCtx = buildTooltipContext(
                    index,
                    series,
                    labels,
                    scales.x,
                    scales.y,
                    canvasBounds,
                    stackedData
                )
                setTooltipCtx(newTooltipCtx)
            }
        },
        [scales, dimensions, labels, series, showTooltip, stackedData, canvasRef]
    )

    const onMouseLeave = useCallback(() => {
        if (!isDragging.current) {
            setHoverIndex(-1)
            setTooltipCtx(null)
        }
    }, [])

    const onMouseDown = useCallback(
        (e: React.MouseEvent<HTMLDivElement>) => {
            if (!scales || !dimensions || !onRangeSelect) {
                return
            }
            const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
            const mouseX = e.clientX - rect.left
            const mouseY = e.clientY - rect.top

            if (!isInPlotArea(mouseX, mouseY, dimensions)) {
                return
            }

            const index = findNearestIndex(mouseX, labels, scales.x)
            isDragging.current = true
            setBrushStart({ x: mouseX, index })
            setBrushCurrent(mouseX)
            setTooltipCtx(null)
        },
        [scales, dimensions, labels, onRangeSelect]
    )

    const onMouseUp = useCallback(
        (e: React.MouseEvent<HTMLDivElement>) => {
            if (!isDragging.current || !brushStart || !scales) {
                if (onPointClick && hoverIndex >= 0) {
                    const clickData = buildPointClickData(hoverIndex, series, labels, stackedData)
                    if (clickData) {
                        onPointClick(clickData)
                    }
                }
                return
            }

            isDragging.current = false

            const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
            const mouseX = e.clientX - rect.left
            const endIndex = findNearestIndex(mouseX, labels, scales.x)

            if (endIndex >= 0 && endIndex !== brushStart.index) {
                const startIdx = Math.min(brushStart.index, endIndex)
                const endIdx = Math.max(brushStart.index, endIndex)
                onRangeSelect?.(startIdx, endIdx)
            }

            setBrushStart(null)
            setBrushCurrent(null)
        },
        [brushStart, scales, labels, onPointClick, onRangeSelect, hoverIndex, series, stackedData]
    )

    const onClick = useCallback(() => {
        if (isDragging.current) {
            return
        }
        if (onPointClick && hoverIndex >= 0) {
            const clickData = buildPointClickData(hoverIndex, series, labels, stackedData)
            if (clickData) {
                onPointClick(clickData)
            }
        }
    }, [onPointClick, hoverIndex, series, labels, stackedData])

    return {
        hoverIndex,
        tooltipCtx,
        brushStart,
        brushCurrent,
        isDragging,
        handlers: { onMouseMove, onMouseLeave, onMouseDown, onMouseUp, onClick },
    }
}
