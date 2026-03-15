import { useCallback, useEffect, useState } from 'react'

import { IconPlay } from '@posthog/icons'
import { LemonSkeleton } from '@posthog/lemon-ui'

import api from 'lib/api'
import { TZLabel } from 'lib/components/TZLabel'
import { LemonButton } from 'lib/lemon-ui/LemonButton'
import { Link } from 'lib/lemon-ui/Link'
import { Tooltip } from 'lib/lemon-ui/Tooltip'
import { humanFriendlyDuration } from 'lib/utils'
import { urls } from 'scenes/urls'

interface SessionReplaysWidgetProps {
    tileId: number
    config: Record<string, any>
    refreshKey?: number
    effectiveDateFrom?: string
    effectiveDateTo?: string
}

interface SessionRecording {
    id: string
    start_time: string
    end_time: string
    recording_duration: number
    distinct_id: string
    viewed: boolean
    person?: {
        distinct_ids: string[]
        properties: Record<string, any>
    }
    activity_score?: number
}

const REFRESH_INTERVAL_MS = 120_000

function ActivityIndicator({ score }: { score: number }): JSX.Element {
    const colorClass = score > 70 ? 'text-success' : score >= 30 ? 'text-warning' : 'text-muted'
    const label = score > 70 ? 'High activity' : score >= 30 ? 'Medium' : 'Low'

    return (
        <Tooltip title={`Activity: ${label} (${score})`}>
            <span className={`inline-flex items-center gap-1 ${colorClass}`}>
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
                <span className="text-xs">{score}</span>
            </span>
        </Tooltip>
    )
}

function SessionReplaysWidget({
    tileId,
    config,
    refreshKey,
    effectiveDateFrom,
    effectiveDateTo,
}: SessionReplaysWidgetProps): JSX.Element {
    const [recordings, setRecordings] = useState<SessionRecording[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const fetchRecordings = useCallback(() => {
        const params = new URLSearchParams()
        params.set('limit', '10')
        const dateFrom = effectiveDateFrom || config.date_from
        const dateTo = effectiveDateTo || config.date_to
        if (dateFrom) {
            params.set('date_from', dateFrom)
        }
        if (dateTo) {
            params.set('date_to', dateTo)
        }
        if (config.min_duration) {
            params.set(
                'having_predicates',
                JSON.stringify([
                    {
                        type: 'recording',
                        key: 'duration',
                        value: config.min_duration,
                        operator: 'gt',
                    },
                ])
            )
        }

        api.get(`api/projects/@current/session_recordings/?${params.toString()}`)
            .then((data: any) => {
                setRecordings(data.results || [])
                setLoading(false)
                setError(null)
            })
            .catch(() => {
                setError('Failed to load session recordings')
                setLoading(false)
            })
    }, [config.date_from, config.date_to, config.min_duration, effectiveDateFrom, effectiveDateTo])

    useEffect(() => {
        setLoading(true)
        fetchRecordings()
        const interval = setInterval(fetchRecordings, REFRESH_INTERVAL_MS)
        return () => clearInterval(interval)
    }, [tileId, fetchRecordings, refreshKey])

    if (loading) {
        return (
            <div className="p-3 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-3">
                        <LemonSkeleton className="h-8 w-8 rounded" />
                        <div className="flex-1 space-y-1">
                            <LemonSkeleton className="h-4 w-3/4" />
                            <LemonSkeleton className="h-3 w-1/2" />
                        </div>
                    </div>
                ))}
            </div>
        )
    }

    if (error) {
        return (
            <div className="p-4 flex flex-col items-center justify-center h-full text-muted">
                <IconPlay className="text-3xl mb-2" />
                <span>{error}</span>
                <LemonButton type="secondary" size="small" className="mt-2" onClick={fetchRecordings}>
                    Retry
                </LemonButton>
            </div>
        )
    }

    if (recordings.length === 0) {
        return (
            <div className="p-4 flex flex-col items-center justify-center h-full text-muted">
                <IconPlay className="text-3xl mb-2" />
                <span>No recordings in this time range</span>
            </div>
        )
    }

    return (
        <div className="h-full overflow-auto">
            {recordings.map((recording) => {
                const personLabel =
                    recording.person?.properties?.email || recording.person?.properties?.name || recording.distinct_id

                return (
                    <Link
                        key={recording.id}
                        to={urls.replaySingle(recording.id)}
                        subtle
                        className="group/row flex items-center gap-3 px-3 py-2 hover:bg-surface-secondary border-b border-border-light !no-underline"
                    >
                        <div className="flex items-center justify-center h-8 w-8 rounded bg-surface-secondary shrink-0">
                            <IconPlay className="text-muted text-sm" />
                        </div>
                        <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate">{personLabel}</div>
                            <div className="flex items-center gap-2 text-xs text-muted">
                                <span>{humanFriendlyDuration(recording.recording_duration)}</span>
                                {recording.activity_score != null && (
                                    <ActivityIndicator score={recording.activity_score} />
                                )}
                                <TZLabel time={recording.start_time} className="text-xs" />
                            </div>
                        </div>
                        {!recording.viewed && (
                            <Tooltip title="Not watched yet">
                                <div className="h-2.5 w-2.5 rounded-full bg-primary shrink-0" />
                            </Tooltip>
                        )}
                    </Link>
                )
            })}
        </div>
    )
}

export default SessionReplaysWidget
