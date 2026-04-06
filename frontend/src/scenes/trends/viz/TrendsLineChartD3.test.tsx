import '@testing-library/jest-dom'

import { cleanup, within } from '@testing-library/react'

import { FEATURE_FLAGS } from 'lib/constants'

import { NodeKind } from '~/queries/schema/schema-general'
import { buildTrendsQuery, chart, renderInsight, trendsSeries } from '~/test/insight-testing'

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

describe('TrendsLineChartD3', () => {
    describe('tooltips', () => {
        it('shows the series value and glyph for a single series', async () => {
            renderInsight({ query: buildTrendsQuery(), featureFlags: HOG_CHARTS_FLAG })

            const tooltip = await chart.hoverTooltip(2, trendsSeries.pageviews.labels!.length)

            expect(within(tooltip).getByText('134')).toBeInTheDocument()
            expect(tooltip.querySelector('.graph-series-glyph')).toBeInTheDocument()
        })

        it('shows breakdown values across series', async () => {
            renderInsight({
                query: buildTrendsQuery({
                    series: [{ kind: NodeKind.EventsNode, event: 'Napped', name: 'Napped' }],
                    breakdownFilter: { breakdown: 'hedgehog', breakdown_type: 'event' },
                }),
                featureFlags: HOG_CHARTS_FLAG,
            })

            const tooltip = await chart.hoverTooltip(2, trendsSeries.pageviews.labels!.length)

            expect(within(tooltip).getByText('Spike')).toBeInTheDocument()
            expect(within(tooltip).getByText('Thistle')).toBeInTheDocument()
        })

        it('excludes zero-count series', async () => {
            renderInsight({
                query: buildTrendsQuery({
                    series: [{ kind: NodeKind.EventsNode, event: 'ZeroCounts', name: 'ZeroCounts' }],
                }),
                featureFlags: HOG_CHARTS_FLAG,
            })

            const tooltip = await chart.hoverTooltip(2, trendsSeries.pageviews.labels!.length)

            expect(within(tooltip).getByText('3')).toBeInTheDocument()
            expect(tooltip.textContent).not.toContain('EmptySeries')
        })

        it('renders correctly when series has no action metadata', async () => {
            renderInsight({
                query: buildTrendsQuery({
                    series: [{ kind: NodeKind.EventsNode, event: 'Minimal', name: 'Minimal' }],
                }),
                featureFlags: HOG_CHARTS_FLAG,
            })

            const tooltip = await chart.hoverTooltip(0, trendsSeries.minimal.labels!.length)

            expect(within(tooltip).getByText('1')).toBeInTheDocument()
        })
    })
})
