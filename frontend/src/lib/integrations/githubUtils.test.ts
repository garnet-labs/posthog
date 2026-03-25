import { getGitHubInstallationSettingsUrl, normalizeGitHubRepositoryValue } from './githubUtils'

describe('githubUtils', () => {
    describe('getGitHubInstallationSettingsUrl', () => {
        it('builds the organization-scoped installation URL for org installations', () => {
            expect(
                getGitHubInstallationSettingsUrl({
                    installation_id: '115652094',
                    account: {
                        type: 'Organization',
                        name: 'peakcloudoy',
                    },
                })
            ).toEqual('https://github.com/organizations/peakcloudoy/settings/installations/115652094')
        })

        it('falls back to the user installation URL for non-org installations', () => {
            expect(
                getGitHubInstallationSettingsUrl({
                    installation_id: '115652094',
                    account: {
                        type: 'User',
                        name: 'masa',
                    },
                })
            ).toEqual('https://github.com/settings/installations/115652094')
        })
    })

    describe('normalizeGitHubRepositoryValue', () => {
        it('keeps plain repository names unchanged', () => {
            expect(normalizeGitHubRepositoryValue('posthog')).toEqual('posthog')
        })

        it('extracts the repository name from a legacy owner/repo value', () => {
            expect(normalizeGitHubRepositoryValue('PostHog/posthog')).toEqual('posthog')
        })
    })
})
