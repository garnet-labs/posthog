import { ChartDisplayType, CompareLabelType, TrendResult } from '~/types'

import { buildTrendsConfig, buildTrendsSeries, indexTrendResults } from '../trends'

const baseTrendResult = (overrides: Partial<TrendResult> = {}): TrendResult => ({
    action: { id: '$pageview', type: 'events', order: 0, name: '$pageview' },
    label: '$pageview',
    count: 100,
    data: [10, 20, 30, 40],
    days: ['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04'],
    labels: ['1-Jan', '2-Jan', '3-Jan', '4-Jan'],
    aggregated_value: 100,
    ...overrides,
})

describe('indexTrendResults', () => {
    it('indexes results with sequential ids and colorIndexes', () => {
        const results = [baseTrendResult(), baseTrendResult({ label: '$autocapture', count: 50 })]
        const indexed = indexTrendResults(results, ChartDisplayType.ActionsLineGraph)

        expect(indexed).toHaveLength(2)
        expect(indexed[0].id).toBe(0)
        expect(indexed[1].id).toBe(1)
        expect(indexed[0].seriesIndex).toBe(0)
        expect(indexed[1].seriesIndex).toBe(1)
        expect(typeof indexed[0].colorIndex).toBe('number')
        expect(typeof indexed[1].colorIndex).toBe('number')
    })

    it('sorts bar value display by aggregated_value descending', () => {
        const results = [
            baseTrendResult({ label: 'low', aggregated_value: 10 }),
            baseTrendResult({ label: 'high', aggregated_value: 100 }),
        ]
        const indexed = indexTrendResults(results, ChartDisplayType.ActionsBarValue)

        expect(indexed[0].label).toBe('high')
        expect(indexed[1].label).toBe('low')
    })

    it('sorts pie display by aggregated_value descending', () => {
        const results = [
            baseTrendResult({ label: 'small', aggregated_value: 5 }),
            baseTrendResult({ label: 'big', aggregated_value: 50 }),
        ]
        const indexed = indexTrendResults(results, ChartDisplayType.ActionsPie)

        expect(indexed[0].label).toBe('big')
        expect(indexed[1].label).toBe('small')
    })

    it('sorts compare results with previous before current for unstacked bar', () => {
        const results = [
            baseTrendResult({ compare_label: CompareLabelType.Current, compare: true }),
            baseTrendResult({ compare_label: CompareLabelType.Previous, compare: true }),
        ]
        const indexed = indexTrendResults(results, ChartDisplayType.ActionsUnstackedBar)

        expect(indexed[0].compare_label).toBe(CompareLabelType.Previous)
        expect(indexed[1].compare_label).toBe(CompareLabelType.Current)
    })

    it('filters lifecycle results by toggled lifecycles', () => {
        const results = [
            baseTrendResult({ status: 'new' }),
            baseTrendResult({ status: 'dormant' }),
            baseTrendResult({ status: 'returning' }),
        ]
        const indexed = indexTrendResults(results, ChartDisplayType.ActionsLineGraph, {
            toggledLifecycles: ['new', 'returning'],
        })

        expect(indexed).toHaveLength(2)
        expect(indexed.map((r) => r.status)).toContain('new')
        expect(indexed.map((r) => r.status)).toContain('returning')
        expect(indexed.map((r) => r.status)).not.toContain('dormant')
    })

    it('assigns same colorIndex to current and previous compare series with same label', () => {
        const results = [
            baseTrendResult({
                label: '$pageview',
                compare_label: CompareLabelType.Current,
                compare: true,
                action: { id: '$pageview', type: 'events', order: 0, name: '$pageview' },
            }),
            baseTrendResult({
                label: '$pageview',
                compare_label: CompareLabelType.Previous,
                compare: true,
                action: { id: '$pageview', type: 'events', order: 0, name: '$pageview' },
            }),
        ]
        const indexed = indexTrendResults(results, ChartDisplayType.ActionsLineGraph)

        expect(indexed[0].colorIndex).toBe(indexed[1].colorIndex)
    })
})

describe('buildTrendsSeries', () => {
    it('maps indexed results to Series[]', () => {
        const results = [baseTrendResult()]
        const indexed = indexTrendResults(results, ChartDisplayType.ActionsLineGraph)
        const series = buildTrendsSeries(indexed, ChartDisplayType.ActionsLineGraph, () => '#ff0000')

        expect(series).toHaveLength(1)
        expect(series[0].label).toBe('$pageview')
        expect(series[0].data).toEqual([10, 20, 30, 40])
        expect(series[0].color).toBe('#ff0000')
        expect(series[0].fillArea).toBe(false)
    })

    it('sets fillArea for area graph display', () => {
        const results = [baseTrendResult()]
        const indexed = indexTrendResults(results, ChartDisplayType.ActionsAreaGraph)
        const series = buildTrendsSeries(indexed, ChartDisplayType.ActionsAreaGraph, () => '#ff0000')

        expect(series[0].fillArea).toBe(true)
    })

    it('includes metadata from trend results', () => {
        const results = [baseTrendResult({ breakdown_value: 'Chrome', compare_label: CompareLabelType.Current })]
        const indexed = indexTrendResults(results, ChartDisplayType.ActionsLineGraph)
        const series = buildTrendsSeries(indexed, ChartDisplayType.ActionsLineGraph, () => '#ff0000')

        expect(series[0].meta).toMatchObject({
            breakdown_value: 'Chrome',
            compare_label: CompareLabelType.Current,
        })
    })

    it('includes zero-count series', () => {
        const results = [
            baseTrendResult({ count: 100 }),
            baseTrendResult({ label: 'empty', count: 0, data: [0, 0, 0, 0] }),
        ]
        const indexed = indexTrendResults(results, ChartDisplayType.ActionsLineGraph)
        const series = buildTrendsSeries(indexed, ChartDisplayType.ActionsLineGraph, () => '#ff0000')

        expect(series).toHaveLength(2)
    })
})

describe('buildTrendsConfig', () => {
    it('builds basic config with defaults', () => {
        const config = buildTrendsConfig({
            interval: 'day',
            days: ['2023-01-01', '2023-01-02'],
            timezone: 'UTC',
            yAxisScaleType: undefined,
            isPercentStackView: false,
            goalLines: undefined,
        })

        expect(config.showGrid).toBe(true)
        expect(config.showCrosshair).toBe(true)
        expect(config.pinnableTooltip).toBe(true)
        expect(config.yScaleType).toBe('linear')
        expect(config.percentStackView).toBe(false)
    })

    it('sets log scale when yAxisScaleType is log10', () => {
        const config = buildTrendsConfig({
            interval: 'day',
            days: [],
            timezone: 'UTC',
            yAxisScaleType: 'log10',
            isPercentStackView: false,
            goalLines: undefined,
        })

        expect(config.yScaleType).toBe('log')
    })

    it('maps goal lines', () => {
        const config = buildTrendsConfig({
            interval: 'day',
            days: [],
            timezone: 'UTC',
            yAxisScaleType: undefined,
            isPercentStackView: false,
            goalLines: [{ value: 100, label: 'Target' }],
        })

        expect(config.goalLines).toEqual([{ value: 100, label: 'Target', borderColor: undefined }])
    })

    it('provides an xTickFormatter', () => {
        const config = buildTrendsConfig({
            interval: 'day',
            days: ['2023-01-01', '2023-01-02'],
            timezone: 'UTC',
            yAxisScaleType: undefined,
            isPercentStackView: false,
            goalLines: undefined,
        })

        expect(typeof config.xTickFormatter).toBe('function')
    })
})
