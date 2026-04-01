import type { Meta, StoryObj } from '@storybook/react'
import { BindLogic, useActions, useValues } from 'kea'
import { useEffect } from 'react'

import { FEATURE_FLAGS } from 'lib/constants'
import { largeRecordingJSONL } from 'scenes/session-recordings/__mocks__/large_recording_blob_one'
import largeRecordingEventsJson from 'scenes/session-recordings/__mocks__/large_recording_load_events_one.json'
import largeRecordingMetaJson from 'scenes/session-recordings/__mocks__/large_recording_meta.json'
import largeRecordingWebVitalsEventsPropertiesJson from 'scenes/session-recordings/__mocks__/large_recording_web_vitals_props.json'
import { PlayerInspector } from 'scenes/session-recordings/player/inspector/PlayerInspector'
import { sessionRecordingDataCoordinatorLogic } from 'scenes/session-recordings/player/sessionRecordingDataCoordinatorLogic'
import { sessionRecordingPlayerLogic } from 'scenes/session-recordings/player/sessionRecordingPlayerLogic'

import { mswDecorator, setFeatureFlags } from '~/mocks/browser'

const mockComments = {
    count: 1,
    results: [
        {
            id: '019838f3-1bab-0000-fce8-04be1d6b6fe3',
            created_by: {
                id: 1,
                uuid: '019838c5-64ac-0000-9f43-17f1bf64f508',
                distinct_id: 'xugZUZjVMSe5Ceo67Y1KX85kiQqB4Gp5OSdC02cjsWl',
                first_name: 'fasda',
                last_name: '',
                email: 'paul@posthog.com',
                is_email_verified: false,
                hedgehog_config: null,
                role_at_organization: 'other',
            },
            deleted: false,
            content: 'about seven seconds in there is this comment which is too long',
            version: 0,
            created_at: '2025-07-23T20:21:53.197354Z',
            item_id: '01975ab7-e00e-726f-aada-988b2f7fa053',
            item_context: {
                is_emoji: false,
                time_in_recording: '2024-11-15T09:19:35.620000Z',
            },
            scope: 'recording',
            source_comment: null,
        },
    ],
}

const mockLogs = {
    results: [
        {
            uuid: 'log-001',
            trace_id: 'trace-abc-001',
            span_id: 'span-001',
            body: 'Handling incoming request POST /api/capture',
            attributes: {
                'http.method': 'POST',
                'http.url': '/api/capture',
                session_id: '12345',
            },
            timestamp: '2023-08-11T12:03:40.000Z',
            observed_timestamp: '2023-08-11T12:03:40.000Z',
            severity_text: 'info',
            severity_number: 9,
            level: 'info',
            resource_attributes: { 'service.name': 'capture-service' },
            instrumentation_scope: 'capture-service',
            event_name: '',
        },
        {
            uuid: 'log-002',
            trace_id: 'trace-abc-002',
            span_id: 'span-002',
            body: 'Rate limit check: 85% of quota used',
            attributes: {
                api_key: 'phc_***',
                usage_percent: '85',
                session_id: '12345',
            },
            timestamp: '2023-08-11T12:03:45.000Z',
            observed_timestamp: '2023-08-11T12:03:45.000Z',
            severity_text: 'warn',
            severity_number: 13,
            level: 'warn',
            resource_attributes: { 'service.name': 'rate-limiter' },
            instrumentation_scope: 'rate-limiter',
            event_name: '',
        },
        {
            uuid: 'log-003',
            trace_id: 'trace-abc-003',
            span_id: 'span-003',
            body: 'Failed to process event batch: kafka producer timeout',
            attributes: {
                'error.type': 'KafkaProducerTimeout',
                'batch.size': '500',
                session_id: '12345',
            },
            timestamp: '2023-08-11T12:04:10.000Z',
            observed_timestamp: '2023-08-11T12:04:10.000Z',
            severity_text: 'error',
            severity_number: 17,
            level: 'error',
            resource_attributes: { 'service.name': 'event-processor' },
            instrumentation_scope: 'event-processor',
            event_name: '',
        },
        {
            uuid: 'log-004',
            trace_id: 'trace-abc-004',
            span_id: 'span-004',
            body: 'Session data persisted successfully',
            attributes: {
                session_id: '12345',
                'db.operation': 'INSERT',
            },
            timestamp: '2023-08-11T12:04:30.000Z',
            observed_timestamp: '2023-08-11T12:04:30.000Z',
            severity_text: 'debug',
            severity_number: 5,
            level: 'debug',
            resource_attributes: { 'service.name': 'session-store' },
            instrumentation_scope: 'session-store',
            event_name: '',
        },
    ],
    hasMore: false,
    maxExportableLogs: 10000,
}

const getBaseMswMocks = (hasLogs: boolean): Record<string, Record<string, unknown>> => ({
    get: {
        '/api/environments/:team_id/logs/has_logs/': { hasLogs },
        '/api/projects/:team_id/comments': mockComments,
        '/api/environments/:team_id/session_recordings/:id': largeRecordingMetaJson,
        '/api/environments/:team_id/session_recordings/:id/snapshots': (
            req: { url: { searchParams: { get: (key: string) => string | null } } },
            res: (value: unknown) => unknown,
            ctx: { text: (value: string) => unknown }
        ) => {
            if (req.url.searchParams.get('source') === 'blob_v2') {
                return res(ctx.text(largeRecordingJSONL))
            }
            return [
                200,
                {
                    sources: [
                        {
                            source: 'blob_v2',
                            start_timestamp: '2023-08-11T12:03:36.097000Z',
                            end_timestamp: '2023-08-11T12:04:52.268000Z',
                            blob_key: '0',
                        },
                    ],
                },
            ]
        },
    },
    post: {
        '/api/environments/:team_id/query': (
            req: { body: Record<string, any> },
            res: (value: unknown) => unknown,
            ctx: { json: (value: unknown) => unknown }
        ) => {
            const body = req.body as Record<string, any>

            if (body.query.kind === 'HogQLQuery') {
                if (body.query.query.includes("event in ['$web_vitals']")) {
                    return res(ctx.json(largeRecordingWebVitalsEventsPropertiesJson))
                }
                return res(ctx.json(largeRecordingEventsJson))
            }

            return res(ctx.json({ results: [] }))
        },
        '/api/environments/:team_id/logs/query/': (
            _req: unknown,
            res: (value: unknown) => unknown,
            ctx: { json: (value: unknown) => unknown }
        ) => {
            return res(ctx.json(mockLogs))
        },
    },
    patch: {
        '/api/environments/:team_id/session_recordings/:id': (
            _req: unknown,
            res: (value: unknown) => unknown,
            ctx: { json: (value: unknown) => unknown }
        ) => {
            return res(ctx.json({}))
        },
    },
})

function PlayerInspectorStory({ showLogsFilter = false }: { showLogsFilter?: boolean }): JSX.Element {
    if (showLogsFilter) {
        setFeatureFlags([FEATURE_FLAGS.SESSION_REPLAY_BACKEND_LOGS])
    }

    const dataLogic = sessionRecordingDataCoordinatorLogic({
        sessionRecordingId: '12345',
        playerKey: 'story-template',
    })
    const { sessionPlayerMetaData } = useValues(dataLogic)

    const { loadSnapshots, loadEvents } = useActions(dataLogic)
    loadSnapshots()

    useEffect(() => {
        loadEvents()
    }, [sessionPlayerMetaData]) // oxlint-disable-line react-hooks/exhaustive-deps

    return (
        <div className="flex flex-col gap-2 min-w-96 min-h-120">
            <BindLogic
                logic={sessionRecordingPlayerLogic}
                props={{
                    sessionRecordingId: '12345',
                    playerKey: 'story-template',
                }}
            >
                <PlayerInspector />
            </BindLogic>
        </div>
    )
}

type Story = StoryObj<typeof PlayerInspectorStory>
const meta: Meta<typeof PlayerInspectorStory> = {
    title: 'Components/PlayerInspector',
    component: PlayerInspectorStory,
}
export default meta

export const Default: Story = {
    args: {
        showLogsFilter: false,
    },
    decorators: [mswDecorator(getBaseMswMocks(true))],
}

export const WithLogsFilter: Story = {
    args: {
        showLogsFilter: true,
    },
    decorators: [mswDecorator(getBaseMswMocks(true))],
}

export const WithLogsFilterUpsell: Story = {
    args: {
        showLogsFilter: true,
    },
    decorators: [mswDecorator(getBaseMswMocks(false))],
}
