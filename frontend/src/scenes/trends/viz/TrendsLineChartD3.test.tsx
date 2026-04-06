import '@testing-library/jest-dom'

import { cleanup } from '@testing-library/react'

import { FEATURE_FLAGS } from 'lib/constants'
import { setupJsdom } from 'lib/hog-charts/test-helpers'

import { NodeKind } from '~/queries/schema/schema-general'
import { buildTrendsQuery, chart, renderInsight, trendsSeries } from '~/test/insight-testing'

let cleanupJsdom: () => void

beforeEach(() => {
    cleanupJsdom = setupJsdom()
})

afterEach(() => {
    cleanupJsdom()
    cleanup()
})

const HOG_CHARTS_FLAG = { [FEATURE_FLAGS.PRODUCT_ANALYTICS_HOG_CHARTS]: true }

describe('TrendsLineChartD3', () => {
    describe('tooltips', () => {
        it('shows the series value and glyph for a single series', async () => {
            renderInsight({ query: buildTrendsQuery(), featureFlags: HOG_CHARTS_FLAG })

            const tooltip = await chart.hoverTooltip(2, trendsSeries.pageviews.labels!.length)

            tooltip.row('Pageview').expectValue('134')
            expect(tooltip.element.querySelector('.graph-series-glyph')).toBeInTheDocument()
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

            tooltip.row('Spike').expectValue('3')
        })

        it('excludes zero-count series', async () => {
            renderInsight({
                query: buildTrendsQuery({
                    series: [{ kind: NodeKind.EventsNode, event: 'ZeroCounts', name: 'ZeroCounts' }],
                }),
                featureFlags: HOG_CHARTS_FLAG,
            })

            const tooltip = await chart.hoverTooltip(2, trendsSeries.pageviews.labels!.length)

            tooltip.row('ActiveSeries').expectValue('3')
            tooltip.expectNoRow('EmptySeries')
        })

        it('renders correctly when series has no action metadata', async () => {
            renderInsight({
                query: buildTrendsQuery({
                    series: [{ kind: NodeKind.EventsNode, event: 'Minimal', name: 'Minimal' }],
                }),
                featureFlags: HOG_CHARTS_FLAG,
            })

            const tooltip = await chart.hoverTooltip(0, trendsSeries.minimal.labels!.length)

            tooltip.row('Minimal').expectValue('1')
        })
    })
})
