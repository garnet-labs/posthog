import { MOCK_DEFAULT_TEAM, MOCK_TEAM_ID } from 'lib/api.mock'

import '@testing-library/jest-dom'

import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BindLogic } from 'kea'
import posthog from 'posthog-js'
import Modal from 'react-modal'

import { useMocks } from '~/mocks/jest'
import { initKeaTests } from '~/test/init'

import { recordingDomainEntryToUrlTrigger } from './recordingDomainToUrlTrigger'
import { ReplayAuthorizedDomains } from './ReplayAuthorizedDomains'
import { ReplayAuthorizedDomainsConvertModal } from './ReplayAuthorizedDomainsConvertModal'
import { replayAuthorizedDomainsMigrationModalLogic } from './replayAuthorizedDomainsMigrationModalLogic'
import type { AuthorizedDomainsMigrationSnapshot } from './replayAuthorizedDomainsMigrationTypes'

jest.mock('scenes/session-recordings/components/InternalSurvey/InternalMultipleChoiceSurvey', () => ({
    InternalMultipleChoiceSurvey: (): null => null,
}))

jest.mock('lib/components/AuthorizedUrlList/AuthorizedUrlList', () => ({
    AuthorizedUrlList: (): JSX.Element => <div data-testid="authorized-url-list-mock" />,
}))

function renderModalWithSnapshot(snapshot: AuthorizedDomainsMigrationSnapshot): ReturnType<typeof render> {
    const view = render(
        <BindLogic logic={replayAuthorizedDomainsMigrationModalLogic}>
            <ReplayAuthorizedDomainsConvertModal />
        </BindLogic>
    )
    act(() => {
        replayAuthorizedDomainsMigrationModalLogic.actions.openMigrationModal(snapshot)
    })
    return view
}

describe('Replay authorized domains migration UI', () => {
    let captureSpy: jest.SpyInstance

    beforeAll(() => {
        const appRoot = document.createElement('div')
        appRoot.id = 'jest-modal-root'
        document.body.appendChild(appRoot)
        Modal.setAppElement('#jest-modal-root')
    })

    beforeEach(() => {
        initKeaTests()
        captureSpy = jest.spyOn(posthog, 'capture').mockImplementation(() => {})
    })

    afterEach(() => {
        cleanup()
        replayAuthorizedDomainsMigrationModalLogic.unmount()
        captureSpy.mockRestore()
    })

    it('ReplayAuthorizedDomainsConvertModal maps domains to editable regex and submits patch, capture, and clears recording_domains', async () => {
        let patchBody: Record<string, unknown> | undefined
        useMocks({
            patch: {
                '/api/environments/:team_id': async (req) => {
                    patchBody = (await req.json()) as Record<string, unknown>
                    return [200, { ...MOCK_DEFAULT_TEAM, ...patchBody }]
                },
            },
        })

        const snapshot: AuthorizedDomainsMigrationSnapshot = {
            recording_domains: ['https://a.com'],
            session_recording_url_trigger_config: [],
        }
        const expectedUrl = recordingDomainEntryToUrlTrigger('https://a.com')!.url

        renderModalWithSnapshot(snapshot)

        expect(screen.getByText('https://a.com')).toBeInTheDocument()
        expect(screen.getByDisplayValue(expectedUrl)).toBeInTheDocument()

        await userEvent.click(screen.getByTestId('replay-authorized-domains-convert-and-remove'))

        await waitFor(() => {
            expect(patchBody).not.toBeUndefined()
        })
        expect(patchBody!.recording_domains).toEqual([])
        expect(patchBody!.session_recording_url_trigger_config).toEqual([{ url: expectedUrl, matching: 'regex' }])

        await waitFor(() => {
            expect(captureSpy).toHaveBeenCalledWith(
                'replay_authorized_domains_converted_to_url_triggers',
                expect.objectContaining({
                    team_id: MOCK_TEAM_ID,
                    recording_domains_before: ['https://a.com'],
                    session_recording_url_trigger_config_before: [],
                    submitted_conversions: [{ authorized_domain: 'https://a.com', url_trigger_regex: expectedUrl }],
                })
            )
        })
    })

    it('ReplayAuthorizedDomainsConvertModal shows validation when regex is invalid', async () => {
        useMocks({
            patch: {
                '/api/environments/:team_id': async () => [200, MOCK_DEFAULT_TEAM],
            },
        })

        const snapshot: AuthorizedDomainsMigrationSnapshot = {
            recording_domains: ['https://a.com'],
            session_recording_url_trigger_config: [],
        }

        renderModalWithSnapshot(snapshot)

        const input = screen.getByDisplayValue(recordingDomainEntryToUrlTrigger('https://a.com')!.url)
        await userEvent.clear(input)
        await userEvent.type(input, '(')

        await userEvent.click(screen.getByTestId('replay-authorized-domains-convert-and-remove'))

        expect(await screen.findByText('Invalid regex')).toBeInTheDocument()
        expect(posthog.capture).not.toHaveBeenCalled()
    })

    it('ReplayAuthorizedDomains opens the convert modal from the primary button', async () => {
        render(<ReplayAuthorizedDomains />)

        await userEvent.click(screen.getByTestId('replay-authorized-domains-convert-to-url-triggers'))

        expect(screen.getByText('Convert authorized domains to URL triggers')).toBeInTheDocument()
        expect(screen.getByText('https://recordings.posthog.com/')).toBeInTheDocument()
    })
})
