import { Meta } from '@storybook/react'
import { BindLogic, useActions } from 'kea'
import { useEffect } from 'react'

import { ErrorEventType } from 'lib/components/Errors/types'

import { mswDecorator } from '~/mocks/browser'
import { NodeKind } from '~/queries/schema/schema-general'

import { TEST_EVENTS } from '../../__mocks__/events'
import { StyleVariables } from '../StyleVariables'
import { ExceptionCard } from './ExceptionCard'
import { exceptionCardLogic } from './exceptionCardLogic'

const meta: Meta = {
    title: 'ErrorTracking/ExceptionCard',
    parameters: {
        layout: 'centered',
        viewMode: 'story',
    },
    decorators: [
        mswDecorator({
            post: {
                'api/environments/:team_id/error_tracking/stack_frames/batch_get/': require('../../__mocks__/stack_frames/batch_get'),
            },
        }),
        (Story) => (
            <StyleVariables>
                {/* 👇 Decorators in Storybook also accept a function. Replace <Story/> with Story() to enable it  */}
                <Story />
            </StyleVariables>
        ),
    ],
}

export default meta

////////////////////// Generic stacktraces

export function ExceptionCardBase(): JSX.Element {
    return (
        <div className="w-[800px]">
            <ExceptionCard
                issueId="issue-id"
                issueName="Test Issue"
                loading={false}
                event={TEST_EVENTS['javascript_resolved'] as any}
            />
        </div>
    )
}

export function ExceptionCardNoInApp(): JSX.Element {
    return (
        <div className="w-[800px]">
            <ExceptionCard
                issueId="issue-id"
                issueName="Test Issue"
                loading={false}
                event={TEST_EVENTS['javascript_no_in_app'] as any}
            />
        </div>
    )
}

export function ExceptionCardLoading(): JSX.Element {
    return (
        <div className="w-[800px]">
            <ExceptionCard issueId="issue-id" issueName={null} loading={true} event={undefined} />
        </div>
    )
}
ExceptionCardLoading.tags = ['test-skip']

export function ExceptionCardSessionTimelineWithSteps(): JSX.Element {
    const event = buildSessionTimelineEvent([
        {
            name: 'Button clicked',
            type: 'ui.interaction',
            offset_ms: -2500,
            properties: { selector: '#submit', text: 'Submit' },
        },
        {
            name: 'API request started',
            type: 'http',
            offset_ms: -1200,
            properties: { method: 'POST', path: '/api/demo' },
        },
        {
            name: 'State updated',
            offset_ms: -1200,
            properties: { from: 'idle', to: 'submitting' },
        },
    ])

    return <ExceptionCardSessionTimelineStory event={event} />
}
ExceptionCardSessionTimelineWithSteps.parameters = sessionTimelineParameters(
    buildSessionTimelineEvent([
        {
            name: 'Button clicked',
            type: 'ui.interaction',
            offset_ms: -2500,
            properties: { selector: '#submit', text: 'Submit' },
        },
        {
            name: 'API request started',
            type: 'http',
            offset_ms: -1200,
            properties: { method: 'POST', path: '/api/demo' },
        },
        {
            name: 'State updated',
            offset_ms: -1200,
            properties: { from: 'idle', to: 'submitting' },
        },
    ])
)

export function ExceptionCardSessionTimelineWithoutSteps(): JSX.Element {
    const event = buildSessionTimelineEvent()
    return <ExceptionCardSessionTimelineStory event={event} />
}
ExceptionCardSessionTimelineWithoutSteps.parameters = sessionTimelineParameters(buildSessionTimelineEvent())

export function ExceptionCardSessionTimelineWithMalformedSteps(): JSX.Element {
    const event = buildSessionTimelineEvent([
        {
            name: 'Button clicked',
            type: 'ui.interaction',
            offset_ms: -2500,
            properties: { selector: '#submit', text: 'Submit' },
        },
        {
            bad: 'row',
        },
    ])

    return <ExceptionCardSessionTimelineStory event={event} />
}
ExceptionCardSessionTimelineWithMalformedSteps.parameters = sessionTimelineParameters(
    buildSessionTimelineEvent([
        {
            name: 'Button clicked',
            type: 'ui.interaction',
            offset_ms: -2500,
            properties: { selector: '#submit', text: 'Submit' },
        },
        {
            bad: 'row',
        },
    ])
)

////////////////////// No session ID

const NO_SESSION_STEPS = [
    {
        name: 'Button clicked',
        type: 'ui.interaction',
        offset_ms: -2500,
        properties: { selector: '#submit', text: 'Submit' },
    },
    {
        name: 'API request started',
        type: 'http',
        offset_ms: -1200,
        properties: { method: 'POST', path: '/api/demo' },
    },
    {
        name: 'State updated',
        offset_ms: -800,
        properties: { from: 'idle', to: 'submitting' },
    },
]

export function ExceptionCardNoSessionWithSteps(): JSX.Element {
    const event = buildSessionTimelineEvent(NO_SESSION_STEPS, { sessionId: null })
    return <ExceptionCardSessionTimelineStory event={event} />
}

export function ExceptionCardNoSessionWithoutSteps(): JSX.Element {
    const event = buildSessionTimelineEvent(undefined, { sessionId: null })
    return <ExceptionCardSessionTimelineStory event={event} />
}

//////////////////// Utils

function ExceptionCardSessionTimelineStory({ event }: { event: ErrorEventType }): JSX.Element {
    return (
        <div className="w-[1000px] h-[700px]">
            <BindLogic logic={exceptionCardLogic} props={{ issueId: 'issue-id' }}>
                <OpenSessionTab>
                    <ExceptionCard issueId="issue-id" issueName="Test Issue" loading={false} event={event} />
                </OpenSessionTab>
            </BindLogic>
        </div>
    )
}

function sessionTimelineParameters(event: ErrorEventType): Record<string, any> {
    const exceptionRows = [[event.uuid, event.timestamp, JSON.stringify(event.properties)]]
    const pageRows = [
        ['page-1', '2024-07-09T11:59:50.000Z', 'https://app.example.com/home', 'web'],
        ['page-2', '2024-07-09T11:59:58.000Z', 'https://app.example.com/demo', 'web'],
    ]
    const customRows = [
        ['custom-1', 'form_opened', '2024-07-09T11:59:55.000Z', 'web'],
        ['custom-2', 'button_clicked', '2024-07-09T12:00:02.000Z', 'web'],
    ]
    const logRows = [
        ['2024-07-09T11:59:52.000Z', 'info', 'App initialized'],
        ['2024-07-09T11:59:59.000Z', 'warn', 'Slow network detected'],
        ['2024-07-09T12:00:01.000Z', 'info', 'Form submitted'],
        ['2024-07-09T12:00:04.000Z', 'error', 'Console error before exception'],
    ]

    const filterRows = (rows: any[], timestampIndex: number, query: any): any[] => {
        const after = query.after ? new Date(query.after).getTime() : Number.NEGATIVE_INFINITY
        const before = query.before ? new Date(query.before).getTime() : Number.POSITIVE_INFINITY
        const descending = query.orderBy?.some((clause: string) => clause.includes('DESC'))

        const filtered = rows.filter((row) => {
            const timestamp = new Date(row[timestampIndex]).getTime()
            return timestamp >= after && timestamp <= before
        })

        return filtered.sort((a, b) => {
            const diff = new Date(a[timestampIndex]).getTime() - new Date(b[timestampIndex]).getTime()
            return descending ? -diff : diff
        })
    }

    const queryHandler = async (req: any, res: any, ctx: any): Promise<any> => {
        const body = await req.clone().json()
        const query = body.query

        if (query.kind === NodeKind.EventsQuery) {
            if (query.select?.includes('properties.$current_url')) {
                return res(ctx.json({ results: filterRows(pageRows, 1, query) }))
            }

            if (query.select?.includes('event')) {
                return res(ctx.json({ results: filterRows(customRows, 2, query) }))
            }

            if (query.select?.includes('properties')) {
                return res(ctx.json({ results: filterRows(exceptionRows, 1, query) }))
            }
        }

        if (query.kind === NodeKind.HogQLQuery) {
            return res(ctx.json({ results: filterRows(logRows, 0, query) }))
        }

        return res(ctx.json({ results: [] }))
    }

    return {
        msw: {
            mocks: {
                post: {
                    'api/environments/:team_id/query': queryHandler,
                },
            },
        },
    }
}

function buildSessionTimelineEvent(
    exceptionSteps?: any[],
    { sessionId = 'session-with-steps' }: { sessionId?: string | null } = {}
): ErrorEventType {
    const { $session_id: _dropped, ...baseWithoutSession } = (TEST_EVENTS['javascript_resolved'] as ErrorEventType)
        .properties as any

    const baseProperties = {
        ...baseWithoutSession,
        ...(sessionId != null ? { $session_id: sessionId } : {}),
        $lib: 'web',
    }
    return {
        ...(TEST_EVENTS['javascript_resolved'] as ErrorEventType),
        uuid: 'current-exception-uuid',
        timestamp: '2024-07-09T12:00:05.000Z',
        properties:
            exceptionSteps !== undefined ? { ...baseProperties, $exception_steps: exceptionSteps } : baseProperties,
    }
}

function OpenSessionTab({ children }: { children: JSX.Element }): JSX.Element {
    const { setCurrentTab } = useActions(exceptionCardLogic({ issueId: 'issue-id' }))

    useEffect(() => {
        setCurrentTab('session')
    }, [setCurrentTab])

    return children
}

//////////////////// All Events

function ExceptionCardWrapperAllEvents({
    children,
}: {
    children: (issueId: string, event: Partial<ErrorEventType>) => JSX.Element
}): JSX.Element {
    return (
        <div className="space-y-8">
            {Object.entries(TEST_EVENTS).map(([name, evt]: [string, any]) => {
                return <div key={name}>{children(name, evt)}</div>
            })}
        </div>
    )
}

export function ExceptionCardAllEvents(): JSX.Element {
    return (
        <ExceptionCardWrapperAllEvents>
            {(issueId, event) => (
                <ExceptionCard issueId={issueId} issueName={null} loading={false} event={event as ErrorEventType} />
            )}
        </ExceptionCardWrapperAllEvents>
    )
}
