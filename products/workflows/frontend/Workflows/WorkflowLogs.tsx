import { useValues } from 'kea'
import { type ReactNode, useMemo, useState } from 'react'

import { IconClock } from '@posthog/icons'
import {
    LemonButton,
    LemonCollapse,
    LemonDivider,
    LemonTable,
    ProfilePicture,
    Spinner,
    Tooltip,
} from '@posthog/lemon-ui'

import { ListHog, SleepingHog } from 'lib/components/hedgehogs'
import PropertyFiltersDisplay from 'lib/components/PropertyFilters/components/PropertyFiltersDisplay'
import { TZLabel } from 'lib/components/TZLabel'
import { dayjs } from 'lib/dayjs'
import { LogsViewer } from 'scenes/hog-functions/logs/LogsViewer'

import { batchWorkflowJobsLogic } from './batchWorkflowJobsLogic'
import {
    computePreviewOccurrences,
    fakeUtcToReal,
    isOneTimeSchedule,
    parseRRuleToState,
} from './hogflows/steps/components/rrule-helpers'
import { HogFlowBatchJob } from './hogflows/types'
import { renderWorkflowLogMessage } from './logs/log-utils'
import { WorkflowLogicProps, workflowLogic } from './workflowLogic'

export type WorkflowLogsProps = {
    id: string
}

function WorkflowRunLogs(props: WorkflowLogsProps): JSX.Element {
    const { workflow } = useValues(workflowLogic)

    return (
        <LogsViewer
            sourceType="hog_flow"
            sourceId={props.id!}
            instanceLabel="workflow run"
            renderMessage={(m) => renderWorkflowLogMessage(workflow, m)}
        />
    )
}

function BatchRunHeader({ job }: { job: HogFlowBatchJob }): JSX.Element {
    return (
        <div className="flex gap-2 w-full justify-between">
            <strong>{job.id}</strong>
            <div className="flex items-center gap-2">
                {job.scheduled_at && (
                    <Tooltip title="This job was scheduled to run in advance" placement="left">
                        <div className="flex items-center gap-2 text-muted">
                            <IconClock className="text-lg" />
                            <TZLabel title="Scheduled at" time={job.scheduled_at} />
                            {' ⋅ '}
                        </div>
                    </Tooltip>
                )}
                <TZLabel title="Created at" time={job.created_at} />
                <LemonDivider vertical className="h-full" />

                {job.created_by ? (
                    <Tooltip title={`Triggered by ${job.created_by.email}`}>
                        <div>
                            <ProfilePicture user={{ email: job.created_by.email }} showName size="sm" />
                        </div>
                    </Tooltip>
                ) : (
                    <span className="text-muted text-sm">Scheduled run</span>
                )}
            </div>
        </div>
    )
}

function BatchRunInfo({ job }: { job: HogFlowBatchJob }): JSX.Element {
    const { workflow } = useValues(workflowLogic)

    const isFutureJob = job.scheduled_at && dayjs(job.scheduled_at).isAfter(dayjs())

    const logsSection = isFutureJob ? (
        <div className="flex flex-col w-full bg-surface-primary rounded py-8 items-center text-center">
            <SleepingHog width="100" height="100" className="mb-4" />
            <h2 className="text-xl leading-tight">This job hasn't started yet</h2>
            <p className="text-sm text-balance text-tertiary">Once the job starts executing, logs will appear here.</p>
        </div>
    ) : (
        <LogsViewer
            sourceType="hog_flow"
            sourceId={job.id}
            groupByInstanceId
            instanceLabel="workflow job"
            renderMessage={(m) => renderWorkflowLogMessage(workflow, m)}
        />
    )

    return (
        <div className="flex flex-col gap-2">
            <div className="flex flex-col gap-2 items-start w-full">
                <span className="text-muted">Job filters</span>
                <PropertyFiltersDisplay
                    filters={Array.isArray(job.filters?.properties) ? job.filters.properties : []}
                />
            </div>
            <span className="text-muted">Logs</span>
            {logsSection}
        </div>
    )
}

const COMPACT_VISIBLE = 2

interface UpcomingOccurrence {
    date: Date
    real: dayjs.Dayjs
    displayDate: string
    displayTime: string
}

function UpcomingOccurrences(): JSX.Element | null {
    const { currentSchedule } = useValues(workflowLogic)
    const [expanded, setExpanded] = useState(false)

    const timezone = currentSchedule?.timezone

    const occurrences = useMemo(() => {
        if (!currentSchedule?.rrule || isOneTimeSchedule(currentSchedule.rrule)) {
            return []
        }
        const parsed = parseRRuleToState(currentSchedule.rrule)
        return computePreviewOccurrences(parsed, currentSchedule.starts_at, currentSchedule.timezone)
    }, [currentSchedule])

    const tzSuffix = timezone && timezone !== dayjs.tz.guess() ? ` ${timezone}` : ''

    const futureOccurrences: UpcomingOccurrence[] = occurrences
        .map((date) => {
            const d = dayjs(date).utc()
            return {
                date,
                real: fakeUtcToReal(date, timezone),
                displayDate: d.format('ddd, MMM D YYYY'),
                displayTime: d.format('h:mm A') + tzSuffix,
            }
        })
        .filter((o) => o.real.isAfter(dayjs()))

    if (futureOccurrences.length === 0) {
        return null
    }

    const hasMore = futureOccurrences.length > COMPACT_VISIBLE
    const visible = expanded ? futureOccurrences : futureOccurrences.slice(0, COMPACT_VISIBLE)

    return (
        <div>
            <SectionHeading>Upcoming</SectionHeading>
            <LemonTable
                dataSource={visible}
                columns={[
                    {
                        title: 'Date',
                        render: (_, row) => row.displayDate,
                    },
                    {
                        title: 'Time',
                        render: (_, row) => row.displayTime,
                    },
                    {
                        title: '',
                        align: 'right' as const,
                        render: (_, row) => <span className="text-muted whitespace-nowrap">{row.real.fromNow()}</span>,
                    },
                ]}
                rowKey={(row) => row.date.toISOString()}
                size="small"
                footer={
                    hasMore ? (
                        <LemonButton fullWidth center onClick={() => setExpanded(!expanded)}>
                            {expanded
                                ? 'Show less'
                                : `Show ${futureOccurrences.length - COMPACT_VISIBLE} more upcoming`}
                        </LemonButton>
                    ) : undefined
                }
            />
        </div>
    )
}

function SectionHeading({ children }: { children: ReactNode }): JSX.Element {
    return <h3 className="text-xs font-semibold uppercase tracking-wide text-muted mb-1">{children}</h3>
}

function WorkflowBatchRunLogs(props: WorkflowLogicProps): JSX.Element {
    const { futureJobs, pastJobs, batchWorkflowJobsLoading } = useValues(batchWorkflowJobsLogic(props))
    const { currentSchedule } = useValues(workflowLogic)
    const hasSchedule = !!currentSchedule?.rrule && !isOneTimeSchedule(currentSchedule.rrule)

    if (batchWorkflowJobsLoading) {
        return (
            <div className="flex justify-center">
                <Spinner size="medium" />
            </div>
        )
    }

    if (!futureJobs.length && !pastJobs.length) {
        return (
            <div className="flex flex-col gap-4">
                <UpcomingOccurrences />
                <div className="flex flex-col bg-surface-primary rounded px-4 py-8 items-center text-center mx-auto">
                    <ListHog width="100" height="100" className="mb-4" />
                    <h2 className="text-xl leading-tight">No batch workflow jobs have been run yet</h2>
                    <p className="text-sm text-balance text-tertiary">
                        Once a batch workflow job is triggered, execution logs will appear here.
                    </p>
                </div>
            </div>
        )
    }

    const pastJobsSection = pastJobs.length ? (
        <LemonCollapse
            panels={pastJobs.map((job) => ({
                key: job.id,
                header: <BatchRunHeader job={job} />,
                content: <BatchRunInfo job={job} />,
            }))}
        />
    ) : (
        <div className="border rounded bg-surface-primary p-2 text-muted">No past invocations yet.</div>
    )

    return (
        <div className="flex flex-col gap-4">
            <UpcomingOccurrences />
            <div>
                {hasSchedule && <SectionHeading>Past invocations</SectionHeading>}
                {pastJobsSection}
            </div>
        </div>
    )
}

export function WorkflowLogs({ id }: WorkflowLogsProps): JSX.Element {
    const { workflow } = useValues(workflowLogic)

    return (
        <div data-attr="workflow-logs">
            {workflow?.trigger?.type === 'batch' ? <WorkflowBatchRunLogs id={id} /> : <WorkflowRunLogs id={id} />}
        </div>
    )
}
