/** Human-readable tool id for TTS (snake_case → words). */
export function humanizeToolName(name: string): string {
    return name.replace(/_/g, ' ').replace(/\s+/g, ' ').trim()
}

/**
 * One short sentence naming the tools being invoked (voice mode narration).
 */
export function sentenceForToolNames(names: string[]): string | null {
    const filtered = [...new Set(names.map((n) => n.trim()).filter(Boolean))]
    if (filtered.length === 0) {
        return null
    }
    const human = filtered.map((n) => humanizeToolName(n))
    if (human.length === 1) {
        return `I'm using ${human[0]}.`
    }
    if (human.length === 2) {
        return `I'm using ${human[0]} and ${human[1]}.`
    }
    return `I'm using ${human.slice(0, -1).join(', ')}, and ${human[human.length - 1]}.`
}
