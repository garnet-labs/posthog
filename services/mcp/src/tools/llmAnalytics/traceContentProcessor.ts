/**
 * Post-processing for LLM trace query results.
 *
 * Strips or truncates large properties ($ai_input, $ai_output_choices,
 * $ai_input_state, $ai_output_state, $ai_tools) to prevent context window
 * overflow in MCP clients.
 */

export type ContentDetail = 'none' | 'preview' | 'full'

const PREVIEW_HEAD = 300
const PREVIEW_TAIL = 300

/** Property keys that can be very large and should be controlled */
const LARGE_EVENT_PROPERTIES = [
    '$ai_input',
    '$ai_output_choices',
    '$ai_input_state',
    '$ai_output_state',
    '$ai_tools',
    '$ai_tools_available',
]

const LARGE_TRACE_FIELDS = ['inputState', 'outputState']

function stringifyValue(value: unknown): string {
    if (typeof value === 'string') {
        return value
    }
    return JSON.stringify(value)
}

function truncateValue(value: unknown): string {
    const str = stringifyValue(value)
    if (str.length <= PREVIEW_HEAD + PREVIEW_TAIL + 50) {
        return str
    }
    const truncatedCount = str.length - PREVIEW_HEAD - PREVIEW_TAIL
    return `${str.slice(0, PREVIEW_HEAD)}... [${truncatedCount} chars truncated] ...${str.slice(-PREVIEW_TAIL)}`
}

function processEventProperties(
    properties: Record<string, unknown>,
    contentDetail: ContentDetail
): Record<string, unknown> {
    if (contentDetail === 'full') {
        return properties
    }

    const result: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(properties)) {
        if (LARGE_EVENT_PROPERTIES.includes(key)) {
            if (contentDetail === 'none') {
                const str = stringifyValue(value)
                result[key] = `[${str.length} chars]`
            } else {
                result[key] = truncateValue(value)
            }
        } else {
            result[key] = value
        }
    }
    return result
}

interface TraceEvent {
    properties: Record<string, unknown>
    [key: string]: unknown
}

interface TraceResult {
    events: TraceEvent[]
    [key: string]: unknown
}

function processTrace(trace: TraceResult, contentDetail: ContentDetail): TraceResult {
    if (contentDetail === 'full') {
        return trace
    }

    const processed = { ...trace }

    for (const field of LARGE_TRACE_FIELDS) {
        if (processed[field] != null) {
            if (contentDetail === 'none') {
                const str = stringifyValue(processed[field])
                processed[field] = `[${str.length} chars]`
            } else {
                processed[field] = truncateValue(processed[field])
            }
        }
    }

    if (Array.isArray(processed.events)) {
        processed.events = processed.events.map((event) => ({
            ...event,
            properties: processEventProperties(event.properties || {}, contentDetail),
        }))
    }

    return processed
}

/**
 * Process trace query results with the specified content detail level.
 * Works for both TracesQuery (list) and TraceQuery (single) results.
 */
export function processTraceResults(results: unknown, contentDetail: ContentDetail): unknown {
    if (contentDetail === 'full') {
        return results
    }

    if (Array.isArray(results)) {
        return results.map((trace) => processTrace(trace as TraceResult, contentDetail))
    }

    return results
}
