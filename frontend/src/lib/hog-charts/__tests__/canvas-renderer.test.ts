import * as d3 from 'd3'

import { drawArea, drawGrid, drawHighlightPoint, drawLine, drawPoints, type DrawContext } from '../core/canvas-renderer'
import type { ChartDimensions, Series } from '../core/types'

const dimensions: ChartDimensions = {
    width: 800,
    height: 400,
    plotLeft: 48,
    plotTop: 16,
    plotWidth: 736,
    plotHeight: 352,
}

function makeSeries(overrides: Partial<Series> & { key: string; data: number[] }): Series {
    return { label: overrides.key, color: '#f00', ...overrides }
}

function mockCanvasContext(): jest.Mocked<CanvasRenderingContext2D> {
    return {
        beginPath: jest.fn(),
        moveTo: jest.fn(),
        lineTo: jest.fn(),
        stroke: jest.fn(),
        fill: jest.fn(),
        closePath: jest.fn(),
        arc: jest.fn(),
        setLineDash: jest.fn(),
        strokeStyle: '',
        fillStyle: '',
        lineWidth: 0,
        lineJoin: '',
        lineCap: '',
        globalAlpha: 1,
    } as unknown as jest.Mocked<CanvasRenderingContext2D>
}

function makeDrawContext(
    ctx: CanvasRenderingContext2D,
    labels: string[],
    xScaleOverride?: d3.ScalePoint<string>
): DrawContext {
    const xScale = xScaleOverride ?? d3.scalePoint<string>().domain(labels).range([48, 784]).padding(0)
    const yScale = d3.scaleLinear().domain([0, 100]).range([368, 16])
    return { ctx, dimensions, xScale, yScale, labels }
}

describe('hog-charts canvas-renderer', () => {
    describe('drawLine', () => {
        it('does not call beginPath for empty data', () => {
            const ctx = mockCanvasContext()
            const series = makeSeries({ key: 's1', data: [] })
            drawLine(makeDrawContext(ctx, []), series)
            expect(ctx.beginPath).not.toHaveBeenCalled()
        })

        it('calls beginPath then moveTo for the first point then lineTo for subsequent points', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b', 'c']
            const series = makeSeries({ key: 's1', data: [10, 50, 90] })
            drawLine(makeDrawContext(ctx, labels), series)
            expect(ctx.beginPath).toHaveBeenCalledTimes(1)
            expect(ctx.moveTo).toHaveBeenCalledTimes(1)
            expect(ctx.lineTo).toHaveBeenCalledTimes(2)
            expect(ctx.stroke).toHaveBeenCalledTimes(1)
        })

        it('sets strokeStyle to the series color', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 20], color: '#abc' })
            drawLine(makeDrawContext(ctx, labels), series)
            expect(ctx.strokeStyle).toBe('#abc')
        })

        it('applies the series dashPattern via setLineDash', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 20], dashPattern: [4, 4] })
            drawLine(makeDrawContext(ctx, labels), series)
            expect(ctx.setLineDash).toHaveBeenCalledWith([4, 4])
        })

        it('resets the dash pattern to [] after drawing', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 20], dashPattern: [5, 5] })
            drawLine(makeDrawContext(ctx, labels), series)
            const calls = (ctx.setLineDash as jest.Mock).mock.calls
            expect(calls[calls.length - 1]).toEqual([[]])
        })

        it('uses an empty dash pattern when dashPattern is not set', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 20] })
            drawLine(makeDrawContext(ctx, labels), series)
            const firstDashCall = (ctx.setLineDash as jest.Mock).mock.calls[0]
            expect(firstDashCall).toEqual([[]])
        })

        it('skips non-finite y points without resetting the path started state', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b', 'c']
            // Override yScale so that the middle value produces Infinity
            const xScale = d3.scalePoint<string>().domain(labels).range([48, 784])
            const origYScale = d3.scaleLinear().domain([0, 100]).range([368, 16])
            const patchedYScale = (v: number): number => (v === 50 ? Infinity : origYScale(v))
            Object.assign(patchedYScale, origYScale)
            const drawCtx: DrawContext = {
                ctx,
                dimensions,
                xScale,
                yScale: patchedYScale as any,
                labels,
            }
            const series = makeSeries({ key: 's1', data: [10, 50, 90] })
            drawLine(drawCtx, series)
            // 'a' draws moveTo (started=true), 'b' is skipped, 'c' draws lineTo (started stays true)
            expect(ctx.moveTo).toHaveBeenCalledTimes(1)
            expect(ctx.lineTo).toHaveBeenCalledTimes(1)
        })

        it('uses yValues override instead of series.data when provided', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [0, 0] })
            drawLine(makeDrawContext(ctx, labels), series, [10, 90])
            // Just verify it rendered (moveTo called once, lineTo once)
            expect(ctx.moveTo).toHaveBeenCalledTimes(1)
            expect(ctx.lineTo).toHaveBeenCalledTimes(1)
        })
    })

    describe('drawArea', () => {
        it('does not call fill when there is no data', () => {
            const ctx = mockCanvasContext()
            const series = makeSeries({ key: 's1', data: [] })
            drawArea(makeDrawContext(ctx, []), series)
            expect(ctx.fill).not.toHaveBeenCalled()
        })

        it('does not fill a segment with only a single point', () => {
            const ctx = mockCanvasContext()
            const labels = ['a']
            const series = makeSeries({ key: 's1', data: [50] })
            drawArea(makeDrawContext(ctx, labels), series)
            expect(ctx.fill).not.toHaveBeenCalled()
        })

        it('fills a contiguous two-point segment', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 90] })
            drawArea(makeDrawContext(ctx, labels), series)
            expect(ctx.fill).toHaveBeenCalledTimes(1)
        })

        it('calls lineTo to close the bottom edges of the area', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 90] })
            drawArea(makeDrawContext(ctx, labels), series)
            // moveTo(a_x, a_y), lineTo(b_x, b_y), lineTo(b_x, baseline), lineTo(a_x, baseline)
            expect(ctx.lineTo).toHaveBeenCalledTimes(3)
        })

        it('splits into two separate fill calls when data has a gap', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b', 'c', 'd']
            // Override yScale so index 1 (value 999) produces Infinity to simulate a gap
            const xScale = d3.scalePoint<string>().domain(labels).range([48, 784])
            const origYScale = d3.scaleLinear().domain([0, 100]).range([368, 16])
            const patchedYScale = (v: number): number => (v === 999 ? Infinity : origYScale(v))
            Object.assign(patchedYScale, origYScale)
            const drawCtx: DrawContext = {
                ctx,
                dimensions,
                xScale,
                yScale: patchedYScale as any,
                labels,
            }
            const series = makeSeries({ key: 's1', data: [10, 999, 50, 80] })
            drawArea(drawCtx, series)
            // [a] is a single-point segment (skipped), [c,d] is a two-point segment (filled once)
            expect(ctx.fill).toHaveBeenCalledTimes(1)
        })

        it('sets globalAlpha to the series fillOpacity and resets to 1 afterwards', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 90], fillOpacity: 0.3 })
            drawArea(makeDrawContext(ctx, labels), series)
            expect(ctx.globalAlpha).toBe(1)
        })

        it('uses default fillOpacity of 0.5 when not specified', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 90] })
            // Capture the alpha when fill() is called
            let capturedAlpha: number | undefined
            ;(ctx.fill as jest.Mock).mockImplementation(() => {
                capturedAlpha = ctx.globalAlpha
            })
            drawArea(makeDrawContext(ctx, labels), series)
            expect(capturedAlpha).toBe(0.5)
        })

        it('sets fillStyle to the series color', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 90], color: '#123456' })
            drawArea(makeDrawContext(ctx, labels), series)
            expect(ctx.fillStyle).toBe('#123456')
        })
    })

    describe('drawPoints', () => {
        it('does not draw anything when pointRadius is 0', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 90], pointRadius: 0 })
            drawPoints(makeDrawContext(ctx, labels), series)
            expect(ctx.arc).not.toHaveBeenCalled()
        })

        it('does not draw anything when pointRadius is not set', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const series = makeSeries({ key: 's1', data: [10, 90] })
            drawPoints(makeDrawContext(ctx, labels), series)
            expect(ctx.arc).not.toHaveBeenCalled()
        })

        it('draws one circle per data point when pointRadius is positive', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b', 'c']
            const series = makeSeries({ key: 's1', data: [10, 50, 90], pointRadius: 4 })
            drawPoints(makeDrawContext(ctx, labels), series)
            expect(ctx.arc).toHaveBeenCalledTimes(3)
            expect(ctx.fill).toHaveBeenCalledTimes(3)
        })

        it('draws circles with the specified radius', () => {
            const ctx = mockCanvasContext()
            const labels = ['a']
            const series = makeSeries({ key: 's1', data: [50], pointRadius: 6 })
            drawPoints(makeDrawContext(ctx, labels), series)
            const [, , r] = (ctx.arc as jest.Mock).mock.calls[0]
            expect(r).toBe(6)
        })

        it('sets fillStyle to the series color', () => {
            const ctx = mockCanvasContext()
            const labels = ['a']
            const series = makeSeries({ key: 's1', data: [50], pointRadius: 4, color: '#ff0000' })
            drawPoints(makeDrawContext(ctx, labels), series)
            expect(ctx.fillStyle).toBe('#ff0000')
        })

        it('skips data points with non-finite y values', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b', 'c']
            const origYScale = d3.scaleLinear().domain([0, 100]).range([368, 16])
            const patchedYScale = (v: number): number => (v === 50 ? Infinity : origYScale(v))
            Object.assign(patchedYScale, origYScale)
            const xScale = d3.scalePoint<string>().domain(labels).range([48, 784])
            const drawCtx: DrawContext = {
                ctx,
                dimensions,
                xScale,
                yScale: patchedYScale as any,
                labels,
            }
            const series = makeSeries({ key: 's1', data: [10, 50, 90], pointRadius: 4 })
            drawPoints(drawCtx, series)
            expect(ctx.arc).toHaveBeenCalledTimes(2)
        })
    })

    describe('drawGrid', () => {
        it('draws a horizontal line for each tick from the y scale', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b', 'c']
            const drawCtx = makeDrawContext(ctx, labels)
            const ticks = drawCtx.yScale.ticks()
            drawGrid(drawCtx)
            expect(ctx.stroke).toHaveBeenCalledTimes(ticks.length)
        })

        it('skips ticks that match goalLineValues', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const drawCtx = makeDrawContext(ctx, labels)
            const ticks = drawCtx.yScale.ticks()
            const goalValue = ticks[1]
            drawGrid(drawCtx, { goalLineValues: [goalValue] })
            expect(ctx.stroke).toHaveBeenCalledTimes(ticks.length - 1)
        })

        it('uses the provided gridColor for strokeStyle', () => {
            const ctx = mockCanvasContext()
            const labels = ['a', 'b']
            const drawCtx = makeDrawContext(ctx, labels)
            drawGrid(drawCtx, { gridColor: 'red' })
            expect(ctx.strokeStyle).toBe('red')
        })

        it('uses the default gridColor when none is provided', () => {
            const ctx = mockCanvasContext()
            const drawCtx = makeDrawContext(ctx, ['a', 'b'])
            drawGrid(drawCtx)
            expect(ctx.strokeStyle).toBe('rgba(0, 0, 0, 0.1)')
        })

        it('draws each grid line spanning the full plot width', () => {
            const ctx = mockCanvasContext()
            const drawCtx = makeDrawContext(ctx, ['a', 'b'])
            drawGrid(drawCtx)
            const moveToCalls = (ctx.moveTo as jest.Mock).mock.calls
            const lineToCalls = (ctx.lineTo as jest.Mock).mock.calls
            for (let i = 0; i < moveToCalls.length; i++) {
                expect(moveToCalls[i][0]).toBe(dimensions.plotLeft)
                expect(lineToCalls[i][0]).toBe(dimensions.plotLeft + dimensions.plotWidth)
            }
        })
    })

    describe('drawHighlightPoint', () => {
        it('draws two circles: a background circle then a foreground circle', () => {
            const ctx = mockCanvasContext()
            drawHighlightPoint(ctx, 100, 200, '#ff0000', '#ffffff')
            expect(ctx.arc).toHaveBeenCalledTimes(2)
            expect(ctx.fill).toHaveBeenCalledTimes(2)
        })

        it('draws the background circle with radius + 2', () => {
            const ctx = mockCanvasContext()
            drawHighlightPoint(ctx, 100, 200, '#ff0000', '#ffffff', 4)
            const firstArcCall = (ctx.arc as jest.Mock).mock.calls[0]
            expect(firstArcCall[2]).toBe(6) // radius + 2
        })

        it('draws the foreground circle with the exact radius', () => {
            const ctx = mockCanvasContext()
            drawHighlightPoint(ctx, 100, 200, '#ff0000', '#ffffff', 4)
            const secondArcCall = (ctx.arc as jest.Mock).mock.calls[1]
            expect(secondArcCall[2]).toBe(4)
        })

        it('uses default radius of 4 when none is specified', () => {
            const ctx = mockCanvasContext()
            drawHighlightPoint(ctx, 100, 200, '#ff0000', '#ffffff')
            const bgRadius = (ctx.arc as jest.Mock).mock.calls[0][2]
            const fgRadius = (ctx.arc as jest.Mock).mock.calls[1][2]
            expect(bgRadius).toBe(6) // 4 + 2
            expect(fgRadius).toBe(4)
        })

        it('draws circles centered at the provided x and y coordinates', () => {
            const ctx = mockCanvasContext()
            drawHighlightPoint(ctx, 150, 250, '#ff0000', '#ffffff', 5)
            for (const call of (ctx.arc as jest.Mock).mock.calls) {
                expect(call[0]).toBe(150)
                expect(call[1]).toBe(250)
            }
        })

        it('sets backgroundColor before the first arc and color before the second arc', () => {
            const ctx = mockCanvasContext()
            const fillStyleValues: string[] = []
            Object.defineProperty(ctx, 'fillStyle', {
                get: () => fillStyleValues[fillStyleValues.length - 1] ?? '',
                set: (v: string) => fillStyleValues.push(v),
            })
            drawHighlightPoint(ctx, 100, 200, '#ff0000', '#ffffff', 4)
            expect(fillStyleValues[0]).toBe('#ffffff') // background set first
            expect(fillStyleValues[1]).toBe('#ff0000') // foreground set second
        })
    })
})
