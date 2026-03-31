import { MOCK_DEFAULT_TEAM } from 'lib/api.mock'

import { Meta, StoryObj } from '@storybook/react'
import { BindLogic, useActions } from 'kea'
import { useLayoutEffect } from 'react'

import { mswDecorator } from '~/mocks/browser'

import { ReplayAuthorizedDomainsConvertModal } from './ReplayAuthorizedDomainsConvertModal'
import { replayAuthorizedDomainsMigrationModalLogic } from './replayAuthorizedDomainsMigrationModalLogic'
import type { AuthorizedDomainsMigrationSnapshot } from './replayAuthorizedDomainsMigrationTypes'

function MigrationModalStoryHost({ snapshot }: { snapshot: AuthorizedDomainsMigrationSnapshot }): JSX.Element {
    const { openMigrationModal } = useActions(replayAuthorizedDomainsMigrationModalLogic)
    useLayoutEffect(() => {
        openMigrationModal(snapshot)
    }, [snapshot, openMigrationModal])
    return <ReplayAuthorizedDomainsConvertModal />
}

const meta: Meta = {
    title: 'Scenes-App/Settings/Replay/Authorized domains convert modal',
    parameters: {
        layout: 'fullscreen',
        viewMode: 'story',
    },
    decorators: [
        mswDecorator({
            patch: {
                '/api/environments/:team_id/': async (req, res, ctx) => {
                    const body = await req.json()
                    return res(ctx.json({ ...MOCK_DEFAULT_TEAM, ...body }))
                },
            },
        }),
    ],
}

export default meta

type Story = StoryObj<{ snapshot: AuthorizedDomainsMigrationSnapshot }>

export const Default: Story = {
    render: ({ snapshot }) => (
        <BindLogic logic={replayAuthorizedDomainsMigrationModalLogic}>
            <MigrationModalStoryHost snapshot={snapshot} />
        </BindLogic>
    ),
    args: {
        snapshot: {
            recording_domains: ['https://*.app.example.com', 'https://app.example.com'],
            session_recording_url_trigger_config: [{ url: '^https://other\\.example\\.com$', matching: 'regex' }],
        },
    },
}

export const SingleDomain: Story = {
    ...Default,
    args: {
        snapshot: {
            recording_domains: ['https://marketing.example.com'],
            session_recording_url_trigger_config: [],
        },
    },
}
