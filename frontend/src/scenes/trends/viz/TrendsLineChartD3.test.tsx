/**
 * Integration tests for TrendsLineChartD3 rendering with real hog-charts components.
 *
 * The hog-charts LineChart/Chart components render for real here — d3 scales compute,
 * interaction hooks run, and the tooltip overlay renders as DOM. The only things mocked
 * are ResizeObserver (jsdom doesn't have it) and canvas draw calls (via jest-canvas-mock
 * which is already in jest.setup.ts). This means tests exercise the full data pipeline:
 * kea → trendsDataLogic → TrendsLineChartD3 → LineChart → scales → overlays → tooltip DOM.
 *
 * The jest.mock below swaps ActionsLineGraph for TrendsLineChartD3 so the existing
 * renderInsightPage helper routes Trends through the hog-charts path without touching
 * production code in Trends.tsx.
 */

// ResizeObserver mock — useChartCanvas needs this to not throw. The initial dimensions
// come from getBoundingClientRect (mocked below), not from the observer callback.
global.ResizeObserver = jest.fn().mockImplementation(() => ({
    observe: jest.fn(),
    unobserve: jest.fn(),
    disconnect: jest.fn(),
})) as any

jest.mock('scenes/trends/viz/ActionsLineGraph', () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { TrendsLineChartD3 } = require('./TrendsLineChartD3')
    return {
        ActionsLineGraph: (props: Record<string, unknown>) => <TrendsLineChartD3 {...props} />,
    }
})

import '@testing-library/jest-dom'

import { act, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'

import { NodeKind } from '~/queries/schema/schema-general'
import { buildTrendsQuery, renderInsightPage, trendsSeries } from '~/test/insight-testing'

// Mock getBoundingClientRect on all elements so the chart gets real dimensions
// and d3 scales compute meaningful values. Without this, useChartCanvas sees 0x0
// and the overlay layer (tooltips, axes) never renders.
const MOCK_RECT = {
    x: 0,
    y: 0,
    width: 800,
    height: 400,
    top: 0,
    left: 0,
    bottom: 400,
    right: 800,
    toJSON: () => ({}),
}

beforeEach(() => {
    jest.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(MOCK_RECT as DOMRect)
})

afterEach(() => {
    jest.restoreAllMocks()
    cleanup()
})

/** Fire a mouseMove on the chart wrapper at a pixel position inside the plot area.
 *  With 800×400 container and default margins (left: 48, right: 16), the plot area
 *  spans x: 48–784. We compute an x position that maps to the desired label index. */
function hoverAtIndex(wrapper: HTMLElement, index: number, totalLabels: number): void {
    const plotLeft = 48
    const plotRight = 800 - 16
    const plotWidth = plotRight - plotLeft
    const step = plotWidth / (totalLabels - 1)
    const clientX = plotLeft + step * index
    const clientY = 200 // vertically centered in plot area
    fireEvent.mouseMove(wrapper, { clientX, clientY })
}

function getChartWrapper(): HTMLElement {
    return screen.getByRole('img', { name: /chart with/i }).parentElement!
}

describe('TrendsLineChartD3 integration', () => {
    it('renders the chart with overlay DOM', async () => {
        renderInsightPage({ query: buildTrendsQuery() })

        await waitFor(() => {
            expect(screen.getByRole('img', { name: /chart with 1 data series/i })).toBeInTheDocument()
        })
    })

    it('shows tooltip with series data on hover', async () => {
        renderInsightPage({ query: buildTrendsQuery() })

        const canvas = await screen.findByRole('img', { name: /chart with/i })
        const wrapper = canvas.parentElement!

        act(() => {
            hoverAtIndex(wrapper, 2, trendsSeries.pageviews.labels!.length)
        })

        await waitFor(() => {
            const tooltip = document.querySelector('[data-hog-charts-tooltip]')
            expect(tooltip).not.toBeNull()
            expect(tooltip!.textContent).toContain('134')
        })
    })

    it('renders multiple series when breakdown is applied', async () => {
        renderInsightPage({
            query: buildTrendsQuery({
                series: [{ kind: NodeKind.EventsNode, event: 'Napped', name: 'Napped' }],
                breakdownFilter: { breakdown: 'hedgehog', breakdown_type: 'event' },
            }),
        })

        await waitFor(() => {
            // napsByHedgehog has 5 series, but Conker has count=0 so TrendsLineChartD3 drops it → 4 visible
            expect(screen.getByRole('img', { name: /chart with 4 data series/i })).toBeInTheDocument()
        })
    })

    it('drops zero-count series from the chart', async () => {
        renderInsightPage({
            query: buildTrendsQuery(),
            mocks: {
                mockResponses: [
                    {
                        match: (q) => q.kind === NodeKind.TrendsQuery,
                        response: {
                            results: [
                                {
                                    action: { id: 'a', type: 'events', name: 'A', order: 0 },
                                    label: 'Empty',
                                    count: 0,
                                    data: [0, 0, 0, 0, 0],
                                    days: ['2024-06-10', '2024-06-11', '2024-06-12', '2024-06-13', '2024-06-14'],
                                    labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                                },
                                {
                                    action: { id: 'b', type: 'events', name: 'B', order: 1 },
                                    label: 'NonEmpty',
                                    count: 10,
                                    data: [1, 2, 3, 2, 2],
                                    days: ['2024-06-10', '2024-06-11', '2024-06-12', '2024-06-13', '2024-06-14'],
                                    labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                                },
                            ],
                        } as any,
                    },
                ],
            },
        })

        await waitFor(() => {
            // Only NonEmpty survives; Empty has count=0 and is filtered out.
            expect(screen.getByRole('img', { name: /chart with 1 data series/i })).toBeInTheDocument()
        })
    })

    it('does not crash when series meta is missing', async () => {
        renderInsightPage({
            query: buildTrendsQuery(),
            mocks: {
                mockResponses: [
                    {
                        match: (q) => q.kind === NodeKind.TrendsQuery,
                        response: {
                            results: [
                                {
                                    label: 'Bare',
                                    count: 5,
                                    data: [1, 1, 1, 1, 1],
                                    days: ['2024-06-10', '2024-06-11', '2024-06-12', '2024-06-13', '2024-06-14'],
                                    labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                                } as any,
                            ],
                        } as any,
                    },
                ],
            },
        })

        await waitFor(() => {
            expect(screen.getByRole('img', { name: /chart with 1 data series/i })).toBeInTheDocument()
        })

        // Hover should not crash even with missing action/breakdown_value/compare_label
        const wrapper = getChartWrapper()
        act(() => {
            hoverAtIndex(wrapper, 0, 5)
        })

        await waitFor(() => {
            const tooltip = document.querySelector('[data-hog-charts-tooltip]')
            expect(tooltip).not.toBeNull()
        })
    })
})
