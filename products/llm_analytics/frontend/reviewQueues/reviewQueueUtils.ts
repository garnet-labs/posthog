export function parseTraceIdsInput(value: string): string[] {
    const dedupedTraceIds = new Set<string>()

    for (const traceId of value
        .split(/[\s,]+/)
        .map((part) => part.trim())
        .filter(Boolean)) {
        dedupedTraceIds.add(traceId)
    }

    return [...dedupedTraceIds]
}

export function formatTraceIdsInput(traceIds: string[]): string {
    return traceIds.join('\n')
}
