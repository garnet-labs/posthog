/**
 * Integration tests for TrendsLineChartD3 with real hog-charts components.
 *
 * Only ResizeObserver and getBoundingClientRect are mocked — everything else
 * (d3 scales, interaction hooks, tooltip overlays) runs for real.
 */

class MockResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
}
global.ResizeObserver = MockResizeObserver

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

const MOCK_RECT: DOMRect = {
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
    jest.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(MOCK_RECT)
})

afterEach(() => {
    jest.restoreAllMocks()
    cleanup()
})

function hoverAtIndex(wrapper: HTMLElement, index: number, totalLabels: number): void {
    const plotLeft = 48
    const plotWidth = 800 - 16 - plotLeft
    const step = plotWidth / (totalLabels - 1)
    fireEvent.mouseMove(wrapper, { clientX: plotLeft + step * index, clientY: 200 })
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

        act(() => {
            hoverAtIndex(canvas.parentElement!, 2, trendsSeries.pageviews.labels!.length)
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
                        },
                    },
                ],
            },
        })

        await waitFor(() => {
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
                                },
                            ],
                        },
                    },
                ],
            },
        })

        await waitFor(() => {
            expect(screen.getByRole('img', { name: /chart with 1 data series/i })).toBeInTheDocument()
        })

        act(() => {
            hoverAtIndex(screen.getByRole('img', { name: /chart with/i }).parentElement!, 0, 5)
        })

        await waitFor(() => {
            expect(document.querySelector('[data-hog-charts-tooltip]')).not.toBeNull()
        })
    })
})
