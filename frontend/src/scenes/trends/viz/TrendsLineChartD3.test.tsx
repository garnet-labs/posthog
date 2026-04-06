import '@testing-library/jest-dom'

import { act, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'

import { FEATURE_FLAGS } from 'lib/constants'
import { DEFAULT_MARGINS } from 'lib/hog-charts/core/Chart'

import { NodeKind } from '~/queries/schema/schema-general'
import { buildTrendsQuery, renderInsightPage, trendsSeries } from '~/test/insight-testing'

class MockResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
}
global.ResizeObserver = MockResizeObserver

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

const HOG_CHARTS_FLAG = { [FEATURE_FLAGS.PRODUCT_ANALYTICS_HOG_CHARTS]: true }

beforeEach(() => {
    jest.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(MOCK_RECT)
})

afterEach(() => {
    jest.restoreAllMocks()
    cleanup()
})

function hoverAtIndex(wrapper: HTMLElement, index: number, totalLabels: number): void {
    const plotLeft = DEFAULT_MARGINS.left
    const plotWidth = MOCK_RECT.width - DEFAULT_MARGINS.right - plotLeft
    const step = plotWidth / (totalLabels - 1)
    fireEvent.mouseMove(wrapper, { clientX: plotLeft + step * index, clientY: 200 })
}

describe('TrendsLineChartD3 integration', () => {
    it('renders the chart with overlay DOM', async () => {
        renderInsightPage({ query: buildTrendsQuery(), featureFlags: HOG_CHARTS_FLAG })

        await waitFor(() => {
            expect(screen.getByRole('img', { name: /chart with 1 data series/i })).toBeInTheDocument()
        })
    })

    it('shows tooltip with series data on hover', async () => {
        renderInsightPage({ query: buildTrendsQuery(), featureFlags: HOG_CHARTS_FLAG })

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
            featureFlags: HOG_CHARTS_FLAG,
        })

        await waitFor(() => {
            expect(screen.getByRole('img', { name: /chart with 4 data series/i })).toBeInTheDocument()
        })
    })

    it('drops zero-count series from the chart', async () => {
        renderInsightPage({
            query: buildTrendsQuery(),
            featureFlags: HOG_CHARTS_FLAG,
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
            featureFlags: HOG_CHARTS_FLAG,
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
