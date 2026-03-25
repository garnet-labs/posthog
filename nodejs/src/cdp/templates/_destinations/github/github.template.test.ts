import { TemplateTester } from '../../test/test-helpers'
import { template } from './github.template'

describe('github template', () => {
    const tester = new TemplateTester(template)

    beforeEach(async () => {
        await tester.beforeEach()
    })

    it('uses the integration owner when the repository input is just the repo name', async () => {
        const response = await tester.invoke({
            github_installation: {
                account: {
                    name: 'PostHog',
                },
                access_token: 'github-token',
            },
            repository: 'posthog',
            title: 'Issue title',
            description: 'Issue description',
            posthog_issue_id: 'issue-123',
        })

        expect(response.error).toBeUndefined()
        expect(response.finished).toEqual(false)
        expect(response.invocation.queueParameters).toMatchObject({
            url: 'https://api.github.com/repos/PostHog/posthog/issues',
        })
    })

    it('uses the owner from a legacy owner/repo repository value', async () => {
        const response = await tester.invoke({
            github_installation: {
                account: {
                    name: 'PostHog',
                },
                access_token: 'github-token',
            },
            repository: 'peakcloudoy/varaus',
            title: 'Issue title',
            description: 'Issue description',
            posthog_issue_id: 'issue-123',
        })

        expect(response.error).toBeUndefined()
        expect(response.finished).toEqual(false)
        expect(response.invocation.queueParameters).toMatchObject({
            url: 'https://api.github.com/repos/peakcloudoy/varaus/issues',
        })
    })
})
