import {
    buildConvertRowsFromAuthorizedDomains,
    computeMigrationMerge,
    mergeNewUrlTriggersIntoExisting,
    normalizeUrlTriggersFromTeam,
    recordingDomainEntryToUrlTrigger,
    validateUrlTriggerPattern,
} from './recordingDomainToUrlTrigger'

describe('recordingDomainEntryToUrlTrigger', () => {
    it('maps a fixed host to a regex that allows any path, query, or hash', () => {
        const t = recordingDomainEntryToUrlTrigger('https://posthog.com')
        expect(t).toEqual({
            url: '^https://posthog\\.com(?:$|[/?#][\\s\\S]*)?$',
            matching: 'regex',
        })
        expect(t?.url && new RegExp(t.url).test('https://posthog.com')).toBe(true)
        expect(t?.url && new RegExp(t.url).test('https://posthog.com/')).toBe(true)
        expect(t?.url && new RegExp(t.url).test('https://posthog.com/pricing')).toBe(true)
        expect(t?.url && new RegExp(t.url).test('https://posthog.com?ref=1')).toBe(true)
        expect(t?.url && new RegExp(t.url).test('https://posthog.com#x')).toBe(true)
    })

    it('maps *.hostname like authorized domains (wildcard only in host)', () => {
        const t = recordingDomainEntryToUrlTrigger('https://*.blah.com')
        expect(t).toEqual({
            url: '^https://.*\\.blah\\.com(?:$|[/?#][\\s\\S]*)?$',
            matching: 'regex',
        })
        expect(t?.url && new RegExp(t.url).test('https://app.blah.com/path')).toBe(true)
        expect(t?.url && new RegExp(t.url).test('https://blah.com/')).toBe(false)
    })

    it('preserves http and ports', () => {
        const t = recordingDomainEntryToUrlTrigger('http://localhost:3000')
        expect(t?.url && new RegExp(t.url).test('http://localhost:3000/')).toBe(true)
    })

    it('returns null for invalid input', () => {
        expect(recordingDomainEntryToUrlTrigger('')).toBe(null)
        expect(recordingDomainEntryToUrlTrigger('not a url')).toBe(null)
    })
})

describe('mergeNewUrlTriggersIntoExisting', () => {
    it('dedupes against existing triggers', () => {
        const existing = [
            {
                url: '^https://posthog\\.com(?:$|[/?#][\\s\\S]*)?$',
                matching: 'regex' as const,
            },
        ]
        const merged = mergeNewUrlTriggersIntoExisting(
            [
                { url: '^https://posthog\\.com(?:$|[/?#][\\s\\S]*)?$', matching: 'regex' },
                { url: '^https://other\\.com(?:$|[/?#][\\s\\S]*)?$', matching: 'regex' },
            ],
            existing
        )
        expect(merged).toHaveLength(2)
    })
})

describe('buildConvertRowsFromAuthorizedDomains', () => {
    it('skips empty strings', () => {
        expect(buildConvertRowsFromAuthorizedDomains(['https://a.com', '', '  '])).toHaveLength(1)
    })
})

describe('validateUrlTriggerPattern', () => {
    it('rejects empty and invalid regex', () => {
        expect(validateUrlTriggerPattern('')).toBe('Pattern is required')
        expect(validateUrlTriggerPattern('(')).toBe('Invalid regex')
        expect(validateUrlTriggerPattern('^ok$')).toBeUndefined()
    })
})

describe('normalizeUrlTriggersFromTeam', () => {
    it('keeps only entries with string url and forces regex matching', () => {
        expect(
            normalizeUrlTriggersFromTeam([{ url: '^a$', matching: 'regex' }, {} as { url: string; matching: 'regex' }])
        ).toEqual([{ url: '^a$', matching: 'regex' }])
    })
})

describe('computeMigrationMerge', () => {
    it('returns errors when any pattern is invalid', () => {
        const r = computeMigrationMerge([{ pattern: '(' }], [])
        expect(r.ok).toBe(false)
        if (!r.ok) {
            expect(r.errors[0]).toBe('Invalid regex')
        }
    })

    it('merges when all patterns valid', () => {
        const u = recordingDomainEntryToUrlTrigger('https://x.com')!.url
        const r = computeMigrationMerge([{ pattern: u }], [])
        expect(r.ok).toBe(true)
        if (r.ok) {
            expect(r.merged).toEqual([{ url: u, matching: 'regex' }])
        }
    })
})
