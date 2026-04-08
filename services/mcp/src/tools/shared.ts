type QueryKind =
    | 'TrendsQuery'
    | 'FunnelsQuery'
    | 'PathsQuery'
    | 'HogQLQuery'
    | 'InsightVizNode'
    | 'DataVisualizationNode'
    | string

interface QueryInfo {
    visualization: 'trends' | 'funnel' | 'paths' | 'table'
    /** The inner query kind (e.g., TrendsQuery inside InsightVizNode) */
    innerKind: QueryKind
    /** The inner query object for insight queries */
    innerQuery?: Record<string, unknown>
}

/** Display types that map to a trends-style (line/bar/area) chart. */
const CHART_DISPLAY_TYPES = new Set([
    'ActionsLineGraph',
    'ActionsBar',
    'ActionsAreaGraph',
    'ActionsLineGraphCumulative',
    'BoldNumber',
    'ActionsPie',
    'ActionsBarValue',
])

/**
 * Analyze the query to determine visualization type and extract inner query info.
 */
export function analyzeQuery(query: unknown): QueryInfo {
    if (!query || typeof query !== 'object') {
        return { visualization: 'table', innerKind: 'unknown' }
    }

    const q = query as Record<string, unknown>

    // Direct insight queries
    if (q.kind === 'TrendsQuery') {
        return { visualization: 'trends', innerKind: 'TrendsQuery', innerQuery: q }
    }
    if (q.kind === 'FunnelsQuery') {
        return { visualization: 'funnel', innerKind: 'FunnelsQuery', innerQuery: q }
    }
    if (q.kind === 'PathsQuery') {
        return { visualization: 'paths', innerKind: 'PathsQuery', innerQuery: q }
    }
    if (q.kind === 'HogQLQuery') {
        return { visualization: 'table', innerKind: 'HogQLQuery' }
    }

    // InsightVizNode wraps insight queries
    if (q.kind === 'InsightVizNode' && q.source && typeof q.source === 'object') {
        const source = q.source as Record<string, unknown>
        if (source.kind === 'TrendsQuery') {
            return { visualization: 'trends', innerKind: 'TrendsQuery', innerQuery: source }
        }
        if (source.kind === 'FunnelsQuery') {
            return { visualization: 'funnel', innerKind: 'FunnelsQuery', innerQuery: source }
        }
        if (source.kind === 'PathsQuery') {
            return { visualization: 'paths', innerKind: 'PathsQuery', innerQuery: source }
        }
    }

    // DataVisualizationNode wraps HogQL queries for custom visualizations
    if (q.kind === 'DataVisualizationNode' && q.source && typeof q.source === 'object') {
        // When a chart display type is set, treat as trends-style visualization
        if (typeof q.display === 'string' && CHART_DISPLAY_TYPES.has(q.display)) {
            return { visualization: 'trends', innerKind: 'HogQLQuery' }
        }
        return { visualization: 'table', innerKind: 'HogQLQuery' }
    }

    return { visualization: 'table', innerKind: String(q.kind || 'unknown') }
}
