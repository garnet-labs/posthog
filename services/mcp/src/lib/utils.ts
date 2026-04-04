import crypto from 'node:crypto'
import { z } from 'zod'

/**
 * PostHog uses UUIDv7-style identifiers where the version nibble can be `0`,
 * which Zod's built-in `.uuid()` rejects (it requires version 1-8 per RFC 9562).
 * This schema accepts any 8-4-4-4-12 hex string so it works with PostHog UUIDs.
 */
export const posthogUuid = () =>
    z
        .string()
        .regex(/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/, 'Invalid UUID')

export function hash(data: string): string {
    // Use PBKDF2 with sufficient computational effort for security
    // 100,000 iterations provides good security while maintaining reasonable performance
    const salt = crypto.createHash('sha256').update('posthog_mcp_salt').digest()
    return crypto.pbkdf2Sync(data, salt, 100000, 32, 'sha256').toString('hex')
}

export function formatPrompt(template: string, vars: Record<string, string>): string {
    return Object.entries(vars)
        .reduce((result, [key, value]) => result.replaceAll(`{${key}}`, value), template)
        .trim()
}

const MAX_HEADER_VALUE_LENGTH = 1000

export function sanitizeHeaderValue(value?: string): string | undefined {
    if (!value) {
        return undefined
    }
    // Strip control characters, then trim and truncate
    const sanitised = value
        .replace(/[\x00-\x1f\x7f]/g, '')
        .trim()
        .slice(0, MAX_HEADER_VALUE_LENGTH)
    return sanitised || undefined
}

export function getSearchParamsFromRecord(
    params: Record<string, string | number | boolean | undefined>
): URLSearchParams {
    const searchParams = new URLSearchParams()

    for (const [key, value] of Object.entries(params)) {
        if (value !== undefined) {
            searchParams.append(key, String(value))
        }
    }

    return searchParams
}
