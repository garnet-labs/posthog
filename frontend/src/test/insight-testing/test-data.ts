import { NodeKind, TrendsQueryResponse } from '~/queries/schema/schema-general'
import { EventDefinition, PropertyDefinition, PropertyType } from '~/types'

const friday = '2024-06-14T16:00:00.000Z'
const setupWeek = '2024-06-03T10:00:00.000Z'

export const days = ['2024-06-10', '2024-06-11', '2024-06-12', '2024-06-13', '2024-06-14']
export const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

export const eventDefinitions: EventDefinition[] = [
    {
        id: 'evt-001',
        name: '$pageview',
        description: 'Scoreboard website viewed',
        tags: ['web'],
        last_seen_at: friday,
        created_at: setupWeek,
    },
    {
        id: 'evt-002',
        name: 'Napped',
        description: 'A hedgehog took a nap',
        tags: ['nap'],
        last_seen_at: friday,
        created_at: setupWeek,
    },
]

export const propertyDefinitions: PropertyDefinition[] = [
    {
        id: 'prop-101',
        name: 'hedgehog',
        description: 'Name of the hedgehog',
        tags: [],
        is_numerical: false,
        property_type: PropertyType.String,
    },
]

export const propertyValues: Record<string, string[]> = {
    hedgehog: ['Spike', 'Bramble', 'Thistle', 'Conker', 'Prickles'],
}

export const personProperties = [
    { id: 1, name: 'email', count: 30 },
    { id: 2, name: 'name', count: 30 },
]

export const sessionPropertyDefinitions: PropertyDefinition[] = [
    {
        id: 'session-001',
        name: '$session_duration',
        description: 'Duration of the session in seconds',
        is_numerical: true,
        property_type: PropertyType.Numeric,
    },
]

export const actionDefinitions: object[] = []

export interface SeriesData {
    label: string
    data: number[]
    labels?: string[]
    days?: string[]
    breakdown_value?: string | number
}

export const trendsSeries = {
    pageviews: {
        label: '$pageview',
        data: [45, 82, 134, 210, 95],
        days,
        labels,
    },
    napped: {
        label: 'Napped',
        data: [1, 3, 5, 8, 2],
        days,
        labels,
    },
    napsByHedgehog: [
        { label: 'Spike', data: [1, 2, 3, 4, 1], days, labels, breakdown_value: 'Spike' },
        { label: 'Bramble', data: [0, 0, 1, 1, 0], days, labels, breakdown_value: 'Bramble' },
        { label: 'Thistle', data: [0, 1, 0, 2, 1], days, labels, breakdown_value: 'Thistle' },
        { label: 'Conker', data: [0, 0, 0, 0, 0], days, labels, breakdown_value: 'Conker' },
        { label: 'Prickles', data: [0, 0, 1, 1, 0], days, labels, breakdown_value: 'Prickles' },
    ],
}

// Maps (event name, optional breakdown) → canned series data.
// The mock query handler calls this to resolve a query into response data.

interface EventSeriesConfig {
    default: SeriesData
    breakdowns?: Record<string, SeriesData[]>
}

const seriesByEvent: Record<string, EventSeriesConfig> = {
    $pageview: { default: trendsSeries.pageviews },
    Napped: {
        default: trendsSeries.napped,
        breakdowns: {
            hedgehog: trendsSeries.napsByHedgehog,
        },
    },
}

const fallbackSeries: SeriesData = {
    label: 'Unknown',
    data: [1, 1, 1, 1, 1],
    days,
    labels,
}

export function lookupSeries(eventName: string, breakdownProperty?: string): SeriesData[] {
    const config = seriesByEvent[eventName]
    if (!config) {
        return [{ ...fallbackSeries, label: eventName }]
    }
    if (breakdownProperty && config.breakdowns?.[breakdownProperty]) {
        return config.breakdowns[breakdownProperty]
    }
    return [config.default]
}

// ---- Ready-made TrendsQueryResponse factories ----
// Each returns a fresh object so tests can't leak state between each other.

function makeResult(label: string, data: number[], extra?: Record<string, unknown>): Record<string, unknown> {
    return {
        action: { id: label, type: 'events', name: label },
        label,
        count: data.reduce((a, b) => a + b, 0),
        data,
        labels: labels.slice(0, data.length),
        days: days.slice(0, data.length),
        ...extra,
    }
}

/** Two series ($pageview + sign_up) with known values. */
export function multiSeriesResponse(): TrendsQueryResponse {
    return {
        results: [makeResult('$pageview', [45, 82, 134, 210, 95]), makeResult('sign_up', [2, 5, 8, 10, 5])],
    } as TrendsQueryResponse
}

/** Same event twice with compare_label current/previous and different data. */
export function compareResponse(): TrendsQueryResponse {
    return {
        results: [
            makeResult('$pageview', [100, 200, 300, 400, 500], {
                compare: true,
                compare_label: 'current',
            }),
            makeResult('$pageview', [50, 75, 100, 125, 150], {
                compare: true,
                compare_label: 'previous',
            }),
        ],
    } as TrendsQueryResponse
}

/** Single data point — tests edge case rendering. */
export function singlePointResponse(): TrendsQueryResponse {
    return {
        results: [makeResult('$pageview', [42])],
    } as TrendsQueryResponse
}

/** One non-zero series + one zero-count series. */
export function zeroCountResponse(): TrendsQueryResponse {
    return {
        results: [
            makeResult('$pageview', [20, 50, 80, 100, 50]),
            { ...makeResult('sign_up', [0, 0, 0, 0, 0]), count: 0 },
        ],
    } as TrendsQueryResponse
}

const weeklyDays = ['2024-06-03', '2024-06-10', '2024-06-17']
const weeklyLabels = ['3 Jun', '10 Jun', '17 Jun']

/** Weekly-aggregated data — used for interval-change tests. */
export function weeklyResponse(): TrendsQueryResponse {
    return {
        results: [
            {
                action: { id: '$pageview', type: 'events', name: '$pageview' },
                label: '$pageview',
                count: 900,
                data: [250, 400, 250],
                labels: weeklyLabels,
                days: weeklyDays,
            },
        ],
    } as TrendsQueryResponse
}

// ---- Mock helper ----

/** Wrap a response factory into a MockResponse that matches TrendsQuery. */
export function makeTrendsMock(response: () => TrendsQueryResponse): {
    match: (query: { kind?: string }) => boolean
    response: () => TrendsQueryResponse
} {
    return {
        match: (query) => query.kind === NodeKind.TrendsQuery,
        response,
    }
}
