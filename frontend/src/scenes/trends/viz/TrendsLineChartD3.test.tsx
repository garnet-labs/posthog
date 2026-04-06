import '@testing-library/jest-dom'

import { act, cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'

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

async function hoverAndGetTooltip(index: number, totalLabels: number): Promise<HTMLElement> {
    const canvas = await screen.findByRole('img', { name: /chart with/i })
    act(() => {
        hoverAtIndex(canvas.parentElement!, index, totalLabels)
    })
    let tooltip!: HTMLElement
    await waitFor(() => {
        const el = document.querySelector('[data-hog-charts-tooltip]')
        expect(el).not.toBeNull()
        tooltip = el as HTMLElement
    })
    return tooltip
}

describe('TrendsLineChartD3', () => {
    it('shows correct series value and label in tooltip on hover', async () => {
        renderInsightPage({ query: buildTrendsQuery(), featureFlags: HOG_CHARTS_FLAG })

        const tooltip = await hoverAndGetTooltip(2, trendsSeries.pageviews.labels!.length)

        expect(within(tooltip).getByText('134')).toBeInTheDocument()
        expect(tooltip.querySelector('.graph-series-glyph')).toBeInTheDocument()
    })

    it('shows breakdown values in tooltip when breakdown is applied', async () => {
        renderInsightPage({
            query: buildTrendsQuery({
                series: [{ kind: NodeKind.EventsNode, event: 'Napped', name: 'Napped' }],
                breakdownFilter: { breakdown: 'hedgehog', breakdown_type: 'event' },
            }),
            featureFlags: HOG_CHARTS_FLAG,
        })

        const tooltip = await hoverAndGetTooltip(2, trendsSeries.pageviews.labels!.length)

        expect(within(tooltip).getByText('Spike')).toBeInTheDocument()
        expect(within(tooltip).getByText('Thistle')).toBeInTheDocument()
    })

    it('excludes zero-count series and shows only active series in tooltip', async () => {
        renderInsightPage({
            query: buildTrendsQuery({
                series: [{ kind: NodeKind.EventsNode, event: 'ZeroCounts', name: 'ZeroCounts' }],
            }),
            featureFlags: HOG_CHARTS_FLAG,
        })

        const tooltip = await hoverAndGetTooltip(2, trendsSeries.pageviews.labels!.length)

        expect(within(tooltip).getByText('3')).toBeInTheDocument()
        expect(tooltip.textContent).not.toContain('EmptySeries')
    })

    it('renders tooltip without crashing when series has no action metadata', async () => {
        renderInsightPage({
            query: buildTrendsQuery({
                series: [{ kind: NodeKind.EventsNode, event: 'Minimal', name: 'Minimal' }],
            }),
            featureFlags: HOG_CHARTS_FLAG,
        })

        const tooltip = await hoverAndGetTooltip(0, trendsSeries.minimal.labels!.length)

        expect(within(tooltip).getByText('1')).toBeInTheDocument()
    })
})
