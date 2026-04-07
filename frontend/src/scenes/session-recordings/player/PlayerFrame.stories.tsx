import type { Meta, StoryObj } from '@storybook/react'
import { BindLogic } from 'kea'

import { recordingMetaJson } from 'scenes/session-recordings/__mocks__/recording_meta'
import { snapshotsAsJSONLines } from 'scenes/session-recordings/__mocks__/recording_snapshots'
import {
    SessionRecordingPlayerMode,
    sessionRecordingPlayerLogic,
} from 'scenes/session-recordings/player/sessionRecordingPlayerLogic'

import { mswDecorator } from '~/mocks/browser'

import { PlayerFrame } from './PlayerFrame'

const meta: Meta<typeof PlayerFrame> = {
    title: 'Replay/Player/PlayerFrame',
    component: PlayerFrame,
    parameters: {
        layout: 'fullscreen',
        viewMode: 'story',
        mockDate: '2023-05-01',
    },
    decorators: [
        mswDecorator({
            get: {
                '/api/environments/:team_id/session_recordings/:id/snapshots': (req, res, ctx) => {
                    if (req.url.searchParams.get('source') === 'blob_v2') {
                        return res(ctx.text(snapshotsAsJSONLines()))
                    }
                    return [
                        200,
                        {
                            sources: [
                                {
                                    source: 'blob_v2',
                                    start_timestamp: '2023-05-01T14:46:20.877000Z',
                                    end_timestamp: '2023-05-01T14:46:32.745000Z',
                                    blob_key: '0',
                                },
                            ],
                        },
                    ]
                },
                '/api/environments/:team_id/session_recordings/:id': () => [200, recordingMetaJson],
            },
        }),
    ],
    render: () => (
        <div style={{ width: 800, height: 500 }} className="relative bg-surface-primary">
            <BindLogic
                logic={sessionRecordingPlayerLogic}
                props={{
                    playerKey: 'storybook',
                    sessionRecordingId: '12345',
                    mode: SessionRecordingPlayerMode.Standard,
                }}
            >
                <PlayerFrame />
            </BindLogic>
        </div>
    ),
}

export default meta
type Story = StoryObj<typeof PlayerFrame>

export const Default: Story = {}
