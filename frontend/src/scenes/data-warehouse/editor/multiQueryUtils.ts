export interface QueryRange {
    /** The SQL text of this individual statement */
    query: string
    /** 0-based character offset where the statement starts in the full input */
    start: number
    /** 0-based character offset where the statement ends in the full input */
    end: number
}

/**
 * Split a multi-statement SQL input into individual queries by splitting on
 * semicolons that are outside of string literals, comments, and parenthesized
 * blocks (subqueries, CTEs, function calls).
 */
export function splitQueries(input: string): QueryRange[] {
    if (!input.trim()) {
        return []
    }

    const ranges: QueryRange[] = []
    let segmentStart = 0
    let i = 0
    let parenDepth = 0

    while (i < input.length) {
        const ch = input[i]

        // Skip over quoted strings
        if (ch === "'" || ch === '"' || ch === '`') {
            i++
            while (i < input.length && input[i] !== ch) {
                if (input[i] === '\\') {
                    i++ // skip escaped character
                }
                i++
            }
            i++ // skip closing quote
            continue
        }

        // Skip single-line comments
        if (ch === '-' && input[i + 1] === '-') {
            i += 2
            while (i < input.length && input[i] !== '\n') {
                i++
            }
            continue
        }

        // Skip block comments
        if (ch === '/' && input[i + 1] === '*') {
            i += 2
            while (i < input.length && !(input[i] === '*' && input[i + 1] === '/')) {
                i++
            }
            i += 2 // skip closing */
            continue
        }

        // Track parenthesis depth — semicolons inside parens are not separators
        if (ch === '(') {
            parenDepth++
            i++
            continue
        }
        if (ch === ')') {
            parenDepth = Math.max(0, parenDepth - 1)
            i++
            continue
        }

        if (ch === ';' && parenDepth === 0) {
            const segment = input.slice(segmentStart, i)
            const trimmed = segment.trim()
            if (trimmed) {
                const trimStart = segmentStart + segment.indexOf(trimmed)
                ranges.push({ query: trimmed, start: trimStart, end: trimStart + trimmed.length })
            }
            segmentStart = i + 1
        }

        i++
    }

    // Remaining text after last semicolon
    const segment = input.slice(segmentStart)
    const trailing = segment.trim()
    if (trailing) {
        const trimStart = segmentStart + segment.indexOf(trailing)
        ranges.push({ query: trailing, start: trimStart, end: trimStart + trailing.length })
    }

    return ranges
}

/**
 * Find the query whose range contains the given cursor offset.
 * If the cursor is between queries (e.g. on a semicolon or whitespace),
 * returns the nearest preceding query. Returns null for empty input.
 */
export function findQueryAtCursor(queries: QueryRange[], cursorOffset: number): QueryRange | null {
    if (queries.length === 0) {
        return null
    }

    // Direct hit — cursor is inside a query range
    for (const q of queries) {
        if (cursorOffset >= q.start && cursorOffset <= q.end) {
            return q
        }
    }

    // Cursor is between queries or after the last one — pick the nearest preceding query
    let best: QueryRange | null = null
    for (const q of queries) {
        if (q.end <= cursorOffset) {
            best = q
        }
    }

    return best ?? queries[0]
}
