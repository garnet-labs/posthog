import type { UrlTriggerConfig } from 'lib/components/IngestionControls/types'

function escapeRegExp(value: string): string {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function recordingDomainEntryToUrlTrigger(domainEntry: string): UrlTriggerConfig | null {
    const trimmed = domainEntry.trim()
    if (!trimmed) {
        return null
    }
    const match = /^([a-zA-Z][a-zA-Z0-9+\-.]*:\/\/)(.+)$/.exec(trimmed)
    if (!match) {
        return null
    }
    const protocol = match[1]
    const host = match[2].replace(/\/+$/, '')
    if (!host) {
        return null
    }
    const hostPattern = escapeRegExp(host).replace(/\\\*/g, '.*')
    const pattern = `^${protocol}${hostPattern}(?:[/?#:][\\s\\S]*)?$`
    try {
        new RegExp(pattern)
    } catch {
        return null
    }
    return { url: pattern, matching: 'regex' }
}

function isUrlTriggerConfig(t: unknown): t is UrlTriggerConfig {
    return !!t && typeof t === 'object' && 'url' in t && typeof (t as UrlTriggerConfig).url === 'string'
}

export function normalizeUrlTriggersFromTeam(raw: UrlTriggerConfig[] | null | undefined): UrlTriggerConfig[] {
    return (raw ?? []).filter(isUrlTriggerConfig).map((t) => ({ url: t.url, matching: 'regex' as const }))
}

export function mergeNewUrlTriggersIntoExisting(
    newTriggers: UrlTriggerConfig[],
    existingTriggers: UrlTriggerConfig[] | null | undefined
): UrlTriggerConfig[] {
    const existing = normalizeUrlTriggersFromTeam(existingTriggers)
    const seen = new Set(existing.map((t) => `${t.matching}:${t.url}`))
    const merged = [...existing]
    for (const t of newTriggers) {
        const normalized = { url: t.url, matching: 'regex' as const }
        const key = `${normalized.matching}:${normalized.url}`
        if (seen.has(key)) {
            continue
        }
        seen.add(key)
        merged.push(normalized)
    }
    return merged
}

export function buildConvertRowsFromAuthorizedDomains(domains: string[]): { domain: string; pattern: string }[] {
    return domains
        .filter((d) => typeof d === 'string' && d.trim() !== '')
        .map((domain) => ({
            domain,
            pattern: recordingDomainEntryToUrlTrigger(domain)?.url ?? '',
        }))
}

export function validateUrlTriggerPattern(pattern: string): string | undefined {
    const trimmed = pattern.trim()
    if (!trimmed) {
        return 'Pattern is required'
    }
    try {
        new RegExp(trimmed)
        return undefined
    } catch {
        return 'Invalid regex'
    }
}

export type MigrationMergeResult =
    | { ok: true; merged: UrlTriggerConfig[] }
    | { ok: false; errors: (string | undefined)[] }

export function computeMigrationMerge(
    rows: { pattern: string }[],
    existingTriggers: UrlTriggerConfig[] | null | undefined
): MigrationMergeResult {
    const errors = rows.map((r) => validateUrlTriggerPattern(r.pattern))
    if (errors.some(Boolean)) {
        return { ok: false, errors }
    }
    const newTriggers: UrlTriggerConfig[] = rows.map((r) => ({
        url: r.pattern.trim(),
        matching: 'regex',
    }))
    return { ok: true, merged: mergeNewUrlTriggersIntoExisting(newTriggers, existingTriggers) }
}
