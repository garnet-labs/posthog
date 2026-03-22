import { cleanup } from '@testing-library/react'
import { waitFor } from '@testing-library/react'

import { NodeKind } from '~/queries/schema/schema-general'
import { ChartDisplayType } from '~/types'

import {
    buildTrendsQuery,
    compare,
    compareResponse,
    display,
    getChart,
    interval,
    makeTrendsMock,
    type MockResponse,
    multiSeriesResponse,
    type QueryBody,
    renderInsightPage,
    singlePointResponse,
    waitForChart,
    weeklyResponse,
    zeroCountResponse,
} from '../../../test/insight-testing'
import { getCapturedChartConfigs } from '../../../test/insight-testing/chartjs-mock'

jest.mock('lib/components/AutoSizer', () => ({
    AutoSizer: ({ renderProp }: { renderProp: (size: { height: number; width: number }) => React.ReactNode }) =>
        renderProp({ height: 400, width: 800 }),
}))

const multiSeriesMock = makeTrendsMock(multiSeriesResponse)

describe.each([
    ['Chart.js (flag off)', {}],
    ['HogLineChart (flag on)', { 'hog-charts': true }],
])('Trends line chart — %s', (_label, featureFlags) => {
    afterEach(cleanup)

    // Tests that need features the hog-charts renderer doesn't support yet
    // use itOrSkip. The test still runs on Chart.js so we know the assertion
    // logic is correct — it's just skipped on the D3 path until wired up.
    const isHogCharts = Object.keys(featureFlags).length > 0
    const itOrSkip = isHogCharts ? it.skip : it

    describe('data correctness', () => {
        it('series data arrays match mock response values exactly', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [
                        { kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' },
                        { kind: NodeKind.EventsNode, event: 'sign_up', name: 'sign_up' },
                    ],
                }),
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.series('$pageview').data).toEqual([45, 82, 134, 210, 95])
            expect(chart.series('sign_up').data).toEqual([2, 5, 8, 10, 5])
        })

        it('value() by numeric index returns the correct data point', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [
                        { kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' },
                        { kind: NodeKind.EventsNode, event: 'sign_up', name: 'sign_up' },
                    ],
                }),
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.value('$pageview', 0)).toBe(45)
            expect(chart.value('$pageview', 2)).toBe(134)
            expect(chart.value('$pageview', 4)).toBe(95)
            expect(chart.value('sign_up', 3)).toBe(10)
        })

        it('value() by label name returns the correct data point', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [
                        { kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' },
                        { kind: NodeKind.EventsNode, event: 'sign_up', name: 'sign_up' },
                    ],
                }),
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.value('$pageview', 'Mon')).toBe(45)
            expect(chart.value('$pageview', 'Wed')).toBe(134)
            expect(chart.value('sign_up', 'Fri')).toBe(5)
        })
    })

    describe('series rendering', () => {
        it('renders all non-zero series from the query response', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [
                        { kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' },
                        { kind: NodeKind.EventsNode, event: 'sign_up', name: 'sign_up' },
                    ],
                }),
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.seriesCount).toBe(2)
            expect(chart.seriesNames).toContain('$pageview')
            expect(chart.seriesNames).toContain('sign_up')
        })

        it('each series has the correct number of data points matching labels', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [
                        { kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' },
                        { kind: NodeKind.EventsNode, event: 'sign_up', name: 'sign_up' },
                    ],
                }),
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.series('$pageview').data).toHaveLength(chart.labels.length)
            expect(chart.series('sign_up').data).toHaveLength(chart.labels.length)
        })

        it('series are not hidden by default', async () => {
            renderInsightPage({
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })
            const chart = await waitForChart()

            expect(chart.series('$pageview').hidden).toBe(false)
        })

        it('series have a color assigned', async () => {
            renderInsightPage({
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })
            const chart = await waitForChart()

            expect(chart.series('$pageview').borderColor).not.toBe('')
        })
    })

    describe('compare to previous', () => {
        it('renders both current and previous series with distinct data values', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [{ kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' }],
                    compareFilter: { compare: true, compare_to: '-7d' },
                }),
                mocks: { mockResponses: [makeTrendsMock(compareResponse)] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.seriesCount).toBe(2)

            const series0 = chart.series(0)
            const series1 = chart.series(1)

            expect(series0.data).toEqual([100, 200, 300, 400, 500])
            expect(series1.data).toEqual([50, 75, 100, 125, 150])

            // Catches bugs where both series get the same data
            expect(series0.data).not.toEqual(series1.data)
        })
    })

    describe('area chart', () => {
        // skip: fillArea not yet captured in hog-charts mock config
        itOrSkip('series have non-transparent backgroundColor indicating area fill', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [{ kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' }],
                    trendsFilter: { display: ChartDisplayType.ActionsAreaGraph },
                }),
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.series('$pageview').backgroundColor).not.toBe('transparent')
            expect(chart.series('$pageview').backgroundColor).not.toBe('')
        })
    })

    describe('log scale', () => {
        it('y-axis uses logarithmic scale type when yAxisScaleType is log10', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    trendsFilter: { yAxisScaleType: 'log10' },
                }),
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.axes.y.type).toBe('logarithmic')
        })
    })

    describe('multiple y-axes', () => {
        it('additional y-axis exists with position set when showMultipleYAxes is true', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [
                        { kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' },
                        { kind: NodeKind.EventsNode, event: 'sign_up', name: 'sign_up' },
                    ],
                    trendsFilter: { showMultipleYAxes: true },
                }),
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.axes.y.display).toBe(true)

            const y1 = chart.axes.y1
            expect(y1).toBeTruthy()
            expect(y1.position).toBeTruthy()
        })
    })

    describe('percent stack view', () => {
        // skip: percentStackView not yet wired in D3 adapter
        itOrSkip('y-axis is stacked when percent stack view is enabled', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [
                        { kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' },
                        { kind: NodeKind.EventsNode, event: 'sign_up', name: 'sign_up' },
                    ],
                    trendsFilter: {
                        display: ChartDisplayType.ActionsAreaGraph,
                        showPercentStackView: true,
                    },
                }),
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.axes.y.stacked).toBe(true)
        })
    })

    describe('y-axis tick formatting', () => {
        // skip: yTickFormatter not yet wired in D3 adapter
        itOrSkip('formats large numbers with abbreviation', async () => {
            renderInsightPage({ featureFlags })
            const chart = await waitForChart()

            const formatted = chart.axes.y.tickLabel(1000)
            expect(formatted).not.toBe('')
            expect(typeof formatted).toBe('string')
        })
    })

    describe('x-axis tick formatting', () => {
        it('has a tick callback that produces formatted output', async () => {
            renderInsightPage({ featureFlags })
            const chart = await waitForChart()

            const xAxis = chart.axes.x
            const formatted = xAxis.tickLabel('2024-06-10')
            expect(typeof formatted).toBe('string')
        })
    })

    describe('goal lines', () => {
        // skip: goal lines not yet captured in hog-charts mock config
        itOrSkip('goal line annotation config appears in chart options', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    trendsFilter: {
                        goalLines: [{ value: 100, label: 'Target', borderColor: '#ff0000' }],
                    },
                }),
                featureFlags,
            })

            const chart = await waitForChart()

            const plugins = (chart.config.options as Record<string, unknown>)?.plugins as
                | Record<string, unknown>
                | undefined
            const annotation = plugins?.annotation as { annotations?: Record<string, unknown> } | undefined
            expect(annotation?.annotations).toBeTruthy()

            const annotationEntries = Object.values(annotation!.annotations!)
            expect(annotationEntries.length).toBeGreaterThanOrEqual(1)

            const firstAnnotation = annotationEntries[0] as Record<string, unknown>
            expect(firstAnnotation.yMin).toBe(100)
            expect(firstAnnotation.yMax).toBe(100)
        })
    })

    describe('single data point', () => {
        it('renders with correct data value for a single-point series', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [{ kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' }],
                }),
                mocks: { mockResponses: [makeTrendsMock(singlePointResponse)] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.seriesCount).toBe(1)
            expect(chart.series('$pageview').data).toEqual([42])
            expect(chart.value('$pageview', 0)).toBe(42)
        })
    })

    describe('zero-count series', () => {
        it('non-zero series has correct data when a zero-count series exists', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    series: [
                        { kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' },
                        { kind: NodeKind.EventsNode, event: 'sign_up', name: 'sign_up' },
                    ],
                }),
                mocks: { mockResponses: [makeTrendsMock(zeroCountResponse)] },
                featureFlags,
            })

            const chart = await waitForChart()

            expect(chart.seriesNames).toContain('$pageview')
            expect(chart.series('$pageview').data).toEqual([20, 50, 80, 100, 50])

            if (Object.keys(featureFlags).length > 0) {
                // D3 path: ActionsLineGraphD3 filters out zero-count series
                expect(chart.seriesCount).toBe(1)
            } else {
                // Chart.js path: zero-count series are included as flat lines
                expect(chart.seriesCount).toBe(2)
            }
        })
    })

    describe('trend lines', () => {
        // skip: showTrendLines not yet captured in hog-charts mock config
        itOrSkip('trend line config is present when showTrendLines is enabled', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    trendsFilter: { showTrendLines: true },
                }),
                featureFlags,
            })

            const chart = await waitForChart()

            const options = chart.config.options as Record<string, unknown>
            const datasets = chart.config.data?.datasets ?? []

            const hasTrendLineOnDataset = datasets.some((ds) => (ds as Record<string, unknown>).trendlineLinear != null)
            const hasTrendLineInOptions = options?.showTrendLines === true

            expect(hasTrendLineOnDataset || hasTrendLineInOptions).toBe(true)
        })
    })

    describe('data labels', () => {
        // skip: showDataLabels not yet captured in hog-charts mock config
        itOrSkip('data labels config is enabled when showValuesOnSeries is true', async () => {
            renderInsightPage({
                query: buildTrendsQuery({
                    trendsFilter: { showValuesOnSeries: true },
                }),
                featureFlags,
            })

            const chart = await waitForChart()

            const plugins = (chart.config.options as Record<string, unknown>)?.plugins as
                | Record<string, unknown>
                | undefined
            expect(plugins?.datalabels).toBeTruthy()
        })
    })

    describe('axes', () => {
        it('x-axis labels come from the query response', async () => {
            renderInsightPage({
                mocks: { mockResponses: [multiSeriesMock] },
                featureFlags,
            })
            const chart = await waitForChart()

            expect(chart.labels).toEqual(['Mon', 'Tue', 'Wed', 'Thu', 'Fri'])
        })

        it('x-axis is visible', async () => {
            renderInsightPage({ featureFlags })
            const chart = await waitForChart()

            expect(chart.axes.x.display).toBe(true)
        })

        it('y-axis is visible', async () => {
            renderInsightPage({ featureFlags })
            const chart = await waitForChart()

            expect(chart.axes.y.display).toBe(true)
        })

        it('y-axis defaults to linear scale', async () => {
            renderInsightPage({ featureFlags })
            const chart = await waitForChart()

            expect(chart.axes.y.type).toBe('linear')
        })
    })

    describe('chart type', () => {
        it('renders as a line chart', async () => {
            renderInsightPage({ featureFlags })
            const chart = await waitForChart()

            expect(chart.type).toBe('line')
        })
    })

    describe('incomplete data', () => {
        beforeEach(() => {
            jest.useFakeTimers({ advanceTimers: true })
            jest.setSystemTime(new Date('2024-06-14T12:00:00Z'))
        })

        afterEach(() => {
            jest.useRealTimers()
        })

        it('still renders all data points when today is incomplete', async () => {
            renderInsightPage({ featureFlags })
            const chart = await waitForChart()

            expect(chart.series('$pageview').data).toHaveLength(5)
        })
    })

    describe('full-stack interactions', () => {
        // After a UI interaction triggers a re-fetch, the chart may
        // re-render multiple times (intermediate states). Poll until
        // the expected condition is met on the latest captured chart.
        async function waitForChartWhere(
            predicate: (chart: ReturnType<typeof getChart>) => void
        ): Promise<ReturnType<typeof getChart>> {
            await waitFor(
                () => {
                    expect(getCapturedChartConfigs().length).toBeGreaterThan(0)
                    const chart = getChart()
                    predicate(chart)
                },
                { timeout: 5000 }
            )
            return getChart()
        }

        it('enabling compare via UI produces two series with distinct data', async () => {
            const initialMock: MockResponse = {
                match: (query: QueryBody) => query.kind === NodeKind.TrendsQuery && !query.compareFilter?.compare,
                response: singlePointResponse,
            }
            const compareMock: MockResponse = {
                match: (query: QueryBody) =>
                    query.kind === NodeKind.TrendsQuery && query.compareFilter?.compare === true,
                response: compareResponse,
            }

            renderInsightPage({
                showFilters: true,
                mocks: { mockResponses: [compareMock, initialMock] },
                featureFlags,
            })

            await waitForChart()

            await compare.enable()
            const chart = await waitForChartWhere((c) => expect(c.seriesCount).toBe(2))

            expect(chart.series(0).data).toEqual([100, 200, 300, 400, 500])
            expect(chart.series(1).data).toEqual([50, 75, 100, 125, 150])
            expect(chart.series(0).data).not.toEqual(chart.series(1).data)
        })

        it('changing interval to week re-fetches with weekly labels', async () => {
            const dailyMock: MockResponse = {
                match: (query: QueryBody) => query.kind === NodeKind.TrendsQuery && query.interval !== 'week',
                response: multiSeriesResponse,
            }
            const weeklyMock: MockResponse = {
                match: (query: QueryBody) => query.kind === NodeKind.TrendsQuery && query.interval === 'week',
                response: weeklyResponse,
            }

            renderInsightPage({
                showFilters: true,
                mocks: { mockResponses: [weeklyMock, dailyMock] },
                featureFlags,
            })

            await waitForChart()

            await interval.set('week')
            const chart = await waitForChartWhere((c) => expect(c.labels).toHaveLength(3))

            expect(chart.labels).toEqual(['3 Jun', '10 Jun', '17 Jun'])
            expect(chart.series('$pageview').data).toEqual([250, 400, 250])
        })

        // skip: display change to area triggers D3 path which captures
        // differently; the Chart.js path verifies the full interaction flow
        itOrSkip('switching display to area chart re-renders with area fill', async () => {
            renderInsightPage({
                showFilters: true,
                featureFlags,
            })

            await waitForChart()

            await display.set('Area chart')
            const chart = await waitForChartWhere((c) => {
                expect(c.seriesCount).toBeGreaterThan(0)
                expect(c.series('$pageview').backgroundColor).not.toBe('transparent')
            })

            expect(chart.series('$pageview').backgroundColor).not.toBe('')
        })
    })
})
