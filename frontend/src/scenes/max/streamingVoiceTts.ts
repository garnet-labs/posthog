/**
 * Incremental text → speakable segments for realtime TTS while the assistant streams.
 * Prefers sentence boundaries; without them, flushes at paragraph/line breaks, then word-wrap at ~maxStreamingChars.
 */

/** While still streaming, never hold more than this without speaking (keeps time-to-first-audio low). */
const MAX_STREAMING_CHARS_WITHOUT_BOUNDARY = 280
/** Rare safety valve for pathological single-line streams */
const MAX_STREAMING_HARD_CAP = 2000

/** Sentence end: punctuation then space or end of string */
function findSentenceEndLength(s: string): number {
    for (let i = 0; i < s.length; i++) {
        const c = s[i]
        if (c === '.' || c === '!' || c === '?' || c === '…') {
            const next = s[i + 1]
            if (next === undefined || /\s/.test(next)) {
                return i + 1
            }
        }
    }
    return -1
}

/** Paragraph break (markdown / model line breaks) */
function findParagraphBreakLength(s: string): number {
    const p = s.indexOf('\n\n')
    if (p >= 0 && p < 800) {
        return p + 2
    }
    return -1
}

/** Single newline: flush a line once we have enough characters (lists, soft wraps) */
function findLineBreakLength(s: string): number {
    const nl = s.indexOf('\n')
    if (nl < 0 || nl < 48) {
        return -1
    }
    return nl + 1
}

export function consumeSpeakableSegmentsFromDelta(
    delta: string,
    isFinal: boolean
): { segments: string[]; consumed: number } {
    const segments: string[] = []
    let pos = 0

    while (pos < delta.length) {
        const rest = delta.slice(pos)
        const endLen = findSentenceEndLength(rest)
        if (endLen > 0) {
            const raw = rest.slice(0, endLen).trim()
            if (raw.length > 0) {
                segments.push(raw)
            }
            let advance = endLen
            while (advance < rest.length && /\s/.test(rest[advance])) {
                advance++
            }
            pos += advance
            continue
        }

        if (!isFinal) {
            const paraLen = findParagraphBreakLength(rest)
            if (paraLen > 0) {
                const raw = rest.slice(0, paraLen).trim()
                if (raw.length > 0) {
                    segments.push(raw)
                }
                pos += paraLen
                continue
            }
            const lineLen = findLineBreakLength(rest)
            if (lineLen > 0) {
                const raw = rest.slice(0, lineLen).trim()
                if (raw.length > 0) {
                    segments.push(raw)
                }
                pos += lineLen
                continue
            }
        }

        if (isFinal && rest.length > 0) {
            const raw = rest.trim()
            if (raw.length > 0) {
                segments.push(raw)
            }
            pos = delta.length
            break
        }

        const maxChunk = isFinal ? MAX_STREAMING_HARD_CAP : MAX_STREAMING_CHARS_WITHOUT_BOUNDARY
        if (rest.length >= maxChunk) {
            let take = maxChunk
            const slice = rest.slice(0, take)
            const lastSpace = slice.lastIndexOf(' ')
            if (lastSpace > 40) {
                take = lastSpace
            }
            const raw = rest.slice(0, take).trim()
            if (raw.length > 0) {
                segments.push(raw)
            }
            pos += take
            while (pos < delta.length && delta[pos] === ' ') {
                pos++
            }
            continue
        }

        break
    }

    return { segments, consumed: pos }
}

export function streamingTtsKey(traceId: string | null | undefined, messageId: string | undefined): string {
    return `${traceId ?? 'none'}:${messageId ?? 'pending'}`
}

/** Longest shared prefix — used when stripMarkdown output shifts so plain no longer extends last snapshot */
export function commonPrefixLength(a: string, b: string): number {
    const n = Math.min(a.length, b.length)
    let i = 0
    while (i < n && a.charCodeAt(i) === b.charCodeAt(i)) {
        i++
    }
    return i
}
