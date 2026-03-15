import { useCallback, useEffect, useState } from 'react'

import { IconLive } from '@posthog/icons'
import { LemonSkeleton } from '@posthog/lemon-ui'

import api from 'lib/api'
import { TZLabel } from 'lib/components/TZLabel'
import { LemonButton } from 'lib/lemon-ui/LemonButton'

interface LogsWidgetProps {
    tileId: number
    config: Record<string, any>
    refreshKey?: number
    effectiveDateFrom?: string
    effectiveDateTo?: string
}

interface LogEntry {
    uuid: string
    timestamp: string
    body: string
    severity_text: string
    service_name?: string
}

const SEVERITY_COLORS: Record<string, string> = {
    trace: 'text-muted',
    debug: 'text-muted',
    info: 'text-primary',
    warn: 'text-warning',
    error: 'text-danger',
    fatal: 'text-danger font-bold',
}

const REFRESH_INTERVAL_MS = 30_000

function LogsWidget({ tileId, config, refreshKey, effectiveDateFrom, effectiveDateTo }: LogsWidgetProps): JSX.Element {
    const [logs, setLogs] = useState<LogEntry[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const fetchLogs = useCallback(() => {
        api.logs
            .query({
                query: {
                    dateRange: {
                        date_from: effectiveDateFrom || config.filters?.dateFrom || '-24h',
                        ...(effectiveDateTo ? { date_to: effectiveDateTo } : {}),
                    },
                    severityLevels: config.filters?.severityLevels || [],
                    serviceNames: config.filters?.serviceNames || [],
                    ...(config.filters?.searchTerm ? { searchTerm: config.filters.searchTerm } : {}),
                    ...(config.filters?.filterGroup ? { filterGroup: config.filters.filterGroup } : {}),
                    limit: 50,
                    orderBy: 'latest',
                },
            })
            .then((data) => {
                setLogs(data.results as unknown as LogEntry[])
                setLoading(false)
                setError(null)
            })
            .catch(() => {
                setError('Failed to load logs')
                setLoading(false)
            })
    }, [config.filters, effectiveDateFrom, effectiveDateTo])

    useEffect(() => {
        setLoading(true)
        fetchLogs()
        const interval = setInterval(fetchLogs, REFRESH_INTERVAL_MS)
        return () => clearInterval(interval)
    }, [tileId, fetchLogs, refreshKey])

    if (loading) {
        return (
            <div className="p-2 space-y-1">
                {Array.from({ length: 8 }).map((_, i) => (
                    <LemonSkeleton key={i} className="h-5 w-full" />
                ))}
            </div>
        )
    }

    if (error) {
        return (
            <div className="p-4 flex flex-col items-center justify-center h-full text-muted">
                <IconLive className="text-3xl mb-2" />
                <span>{error}</span>
                <LemonButton type="secondary" size="small" className="mt-2" onClick={fetchLogs}>
                    Retry
                </LemonButton>
            </div>
        )
    }

    if (logs.length === 0) {
        return (
            <div className="p-4 flex flex-col items-center justify-center h-full text-muted">
                <IconLive className="text-3xl mb-2" />
                <span>No logs in this time range</span>
            </div>
        )
    }

    return (
        <div className="h-full overflow-auto font-mono text-xs">
            {logs.map((log) => (
                <div
                    key={log.uuid}
                    className="flex gap-2 px-2 py-0.5 hover:bg-surface-secondary border-b border-border-light"
                >
                    <TZLabel time={log.timestamp} formatDate="" formatTime="HH:mm:ss" className="text-muted shrink-0" />
                    {log.service_name ? (
                        <span className="text-muted text-[0.65rem] shrink-0 max-w-24 truncate" title={log.service_name}>
                            {log.service_name}
                        </span>
                    ) : null}
                    <span
                        className={`uppercase shrink-0 w-10 text-right ${SEVERITY_COLORS[log.severity_text?.toLowerCase()] || 'text-muted'}`}
                    >
                        {log.severity_text || '---'}
                    </span>
                    <span className="line-clamp-2" title={log.body}>
                        {log.body}
                    </span>
                </div>
            ))}
        </div>
    )
}

export default LogsWidget
