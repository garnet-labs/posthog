import {
    buildConvertRowsFromAuthorizedDomains,
    computeMigrationMerge,
    mergeNewUrlTriggersIntoExisting,
    normalizeUrlTriggersFromTeam,
    recordingDomainEntryToUrlTrigger,
    validateUrlTriggerPattern,
} from './recordingDomainToUrlTrigger'

describe('recordingDomainEntryToUrlTrigger', () => {
    it.each([
        ['https://posthog.com', '^https://posthog\\.com(?:[/?#:][\\s\\S]*)?$'],
        ['https://*.blah.com', '^https://.*\\.blah\\.com(?:[/?#:][\\s\\S]*)?$'],
        ['http://localhost:3000', '^http://localhost:3000(?:[/?#:][\\s\\S]*)?$'],
        ['https://app.example.com:8443', '^https://app\\.example\\.com:8443(?:[/?#:][\\s\\S]*)?$'],
        ['https://*.example.com:9090', '^https://.*\\.example\\.com:9090(?:[/?#:][\\s\\S]*)?$'],
    ])('converts %s to regex %s', (domain, expectedPattern) => {
        expect(recordingDomainEntryToUrlTrigger(domain)).toEqual({
            url: expectedPattern,
            matching: 'regex',
        })
    })

    it.each([
        ['https://posthog.com', 'https://posthog.com', true],
        ['https://posthog.com', 'https://posthog.com/', true],
        ['https://posthog.com', 'https://posthog.com/pricing', true],
        ['https://posthog.com', 'https://posthog.com?ref=1', true],
        ['https://posthog.com', 'https://posthog.com#x', true],
        ['https://posthog.com', 'https://posthog.computer', false],
        ['https://*.blah.com', 'https://app.blah.com/path', true],
        ['https://*.blah.com', 'https://blah.com/', false],
        ['http://localhost:3000', 'http://localhost:3000/', true],
        ['http://localhost:3000', 'http://localhost:30001', false],
        ['https://app.example.com', 'https://app.example.com:8443/page', true],
        ['https://app.example.com:8443', 'https://app.example.com:8443/path', true],
        ['https://app.example.com:8443', 'https://app.example.com:9999/path', false],
        ['https://app.example.com:8443', 'https://app.example.com/path', false],
        ['https://*.example.com:9090', 'https://staging.example.com:9090/', true],
        ['https://*.example.com:9090', 'https://staging.example.com:1111/', false],
    ])('regex from %s matches %s => %s', (domain, url, expected) => {
        const t = recordingDomainEntryToUrlTrigger(domain)
        expect(t).not.toBeNull()
        expect(new RegExp(t!.url).test(url)).toBe(expected)
    })

    it.each([[''], ['not a url'], ['ftp://nope.com']])('returns null for invalid input %s', (domain) => {
        expect(recordingDomainEntryToUrlTrigger(domain)).toBeNull()
    })
})

describe('mergeNewUrlTriggersIntoExisting', () => {
    it('dedupes against existing triggers', () => {
        const existing = [
            {
                url: '^https://posthog\\.com(?:[/?#:][\\s\\S]*)?$',
                matching: 'regex' as const,
            },
        ]
        const merged = mergeNewUrlTriggersIntoExisting(
            [
                { url: '^https://posthog\\.com(?:[/?#:][\\s\\S]*)?$', matching: 'regex' },
                { url: '^https://other\\.com(?:[/?#:][\\s\\S]*)?$', matching: 'regex' },
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
