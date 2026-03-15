import { useCallback, useEffect, useState } from 'react'

import { IconCheck, IconCheckCircle, IconLogomark, IconWarning, IconX } from '@posthog/icons'
import { LemonSkeleton } from '@posthog/lemon-ui'

import api from 'lib/api'
import { TZLabel } from 'lib/components/TZLabel'
import { LemonButton } from 'lib/lemon-ui/LemonButton'
import { lemonToast } from 'lib/lemon-ui/LemonToast/LemonToast'
import { Link } from 'lib/lemon-ui/Link'
import { Tooltip } from 'lib/lemon-ui/Tooltip'
import { humanFriendlyLargeNumber } from 'lib/utils'
import { urls } from 'scenes/urls'

interface ErrorTrackingWidgetProps {
    tileId: number
    config: Record<string, any>
    refreshKey?: number
    effectiveDateFrom?: string
    effectiveDateTo?: string
}

interface ErrorIssue {
    id: string
    name: string
    description: string | null
    status: string
    first_seen: string
    last_seen: string
    occurrences: number
}

const STATUS_BADGE: Record<string, { dot: string; text: string }> = {
    active: { dot: 'bg-warning', text: 'Active' },
    resolved: { dot: 'bg-success', text: 'Resolved' },
    archived: { dot: 'bg-muted', text: 'Archived' },
    pending_release: { dot: 'bg-muted', text: 'Pending release' },
    suppressed: { dot: 'bg-muted', text: 'Suppressed' },
}

const REFRESH_INTERVAL_MS = 60_000

function ErrorTrackingWidget({
    config,
    refreshKey,
    effectiveDateFrom,
    effectiveDateTo,
}: ErrorTrackingWidgetProps): JSX.Element {
    const [issues, setIssues] = useState<ErrorIssue[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [actionInProgress, setActionInProgress] = useState<Record<string, string>>({})
    const [recentlyActioned, setRecentlyActioned] = useState<Set<string>>(new Set())

    const showControls = config.show_controls !== false

    const handleStatusChange = useCallback(
        (issueId: string, newStatus: 'resolved' | 'suppressed', e: React.MouseEvent) => {
            e.preventDefault()
            e.stopPropagation()
            setActionInProgress((prev) => ({ ...prev, [issueId]: newStatus }))
            api.update(`api/environments/@current/error_tracking/issues/${issueId}`, { status: newStatus })
                .then(() => {
                    lemonToast.success(`Issue ${newStatus}`)
                    setRecentlyActioned((prev) => new Set(prev).add(issueId))
                    setTimeout(() => {
                        setIssues((prev) => prev.filter((issue) => issue.id !== issueId))
                        setRecentlyActioned((prev) => {
                            const next = new Set(prev)
                            next.delete(issueId)
                            return next
                        })
                    }, 1500)
                })
                .catch(() => {
                    lemonToast.error(`Failed to ${newStatus === 'resolved' ? 'resolve' : 'suppress'} issue`)
                })
                .finally(() => {
                    setActionInProgress((prev) => {
                        const next = { ...prev }
                        delete next[issueId]
                        return next
                    })
                })
        },
        []
    )

    const fetchIssues = useCallback(() => {
        const params = new URLSearchParams()
        params.set('limit', '10')
        if (config.status) {
            params.set('status', config.status)
        }
        if (config.search_query) {
            params.set('search_query', config.search_query)
        }
        if (config.order_by) {
            params.set('ordering', config.order_by)
        }
        if (effectiveDateFrom) {
            params.set('date_from', effectiveDateFrom)
        }
        if (effectiveDateTo) {
            params.set('date_to', effectiveDateTo)
        }

        api.get(`api/environments/@current/error_tracking/issues/?${params.toString()}`)
            .then((data: any) => {
                setIssues(data.results || [])
                setLoading(false)
                setError(null)
            })
            .catch(() => {
                setError('Failed to load errors')
                setLoading(false)
            })
    }, [config.status, config.search_query, config.order_by, effectiveDateFrom, effectiveDateTo])

    useEffect(() => {
        setLoading(true)
        fetchIssues()
        const interval = setInterval(fetchIssues, REFRESH_INTERVAL_MS)
        return () => clearInterval(interval)
    }, [fetchIssues, refreshKey])

    if (loading) {
        return (
            <div className="p-3 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="space-y-1">
                        <LemonSkeleton className="h-4 w-3/4" />
                        <LemonSkeleton className="h-3 w-full" />
                        <LemonSkeleton className="h-3 w-1/3" />
                    </div>
                ))}
            </div>
        )
    }

    if (error) {
        return (
            <div className="p-4 flex flex-col items-center justify-center h-full text-muted">
                <IconWarning className="text-3xl mb-2" />
                <span>{error}</span>
                <LemonButton
                    type="secondary"
                    size="small"
                    className="mt-2"
                    onClick={() => {
                        setLoading(true)
                        fetchIssues()
                    }}
                >
                    Retry
                </LemonButton>
            </div>
        )
    }

    if (issues.length === 0) {
        return (
            <div className="p-4 flex flex-col items-center justify-center h-full text-muted">
                <IconCheckCircle className="text-3xl mb-2 text-success" />
                <span>No errors in this time range</span>
            </div>
        )
    }

    return (
        <div className="h-full overflow-auto">
            {issues.map((issue) => {
                const badge = STATUS_BADGE[issue.status] || { dot: 'bg-muted', text: issue.status }
                const isActioned = recentlyActioned.has(issue.id)
                const isInProgress = issue.id in actionInProgress
                const alwaysShowActions = false
                return (
                    <Link
                        key={issue.id}
                        to={urls.errorTrackingIssue(issue.id)}
                        subtle
                        className={`group/row block px-3 py-2 border-b border-border-light !no-underline hover:bg-surface-secondary transition-opacity duration-300 ${isActioned ? 'opacity-40' : ''}`}
                    >
                        <div className="flex flex-col gap-[3px]">
                            <div className="flex items-center gap-2">
                                <IconLogomark className="shrink-0 text-muted" fontSize="0.7rem" />
                                <span
                                    title={issue.name || 'Unknown error'}
                                    className="font-semibold text-[0.9rem] line-clamp-1 flex-1"
                                >
                                    {issue.name || 'Unknown error'}
                                </span>
                                {issue.occurrences != null && (
                                    <span className="shrink-0 text-xs font-medium text-muted bg-surface-secondary rounded px-1.5 py-0.5">
                                        {humanFriendlyLargeNumber(issue.occurrences)}
                                    </span>
                                )}
                                {showControls && !isActioned && (
                                    <span
                                        className={`shrink-0 flex items-center gap-1 ${alwaysShowActions ? '' : 'opacity-0 group-hover/row:opacity-100'} transition-opacity`}
                                    >
                                        <Tooltip title="Resolve">
                                            <LemonButton
                                                size="xsmall"
                                                icon={<IconCheck />}
                                                status="success"
                                                loading={isInProgress && actionInProgress[issue.id] === 'resolved'}
                                                onClick={(e) => handleStatusChange(issue.id, 'resolved', e)}
                                            />
                                        </Tooltip>
                                        <Tooltip title="Suppress">
                                            <LemonButton
                                                size="xsmall"
                                                icon={<IconX />}
                                                status="danger"
                                                loading={isInProgress && actionInProgress[issue.id] === 'suppressed'}
                                                onClick={(e) => handleStatusChange(issue.id, 'suppressed', e)}
                                            />
                                        </Tooltip>
                                    </span>
                                )}
                            </div>
                            {issue.description && (
                                <div
                                    title={issue.description}
                                    className="font-medium line-clamp-1 text-[var(--gray-8)]"
                                >
                                    {issue.description}
                                </div>
                            )}
                            <div className="flex items-center text-secondary gap-1">
                                <span className="flex items-center gap-1 text-xs">
                                    <span className={`inline-block h-2 w-2 rounded-full ${badge.dot}`} />
                                    {badge.text}
                                </span>
                                <span className="text-quaternary mx-0.5">|</span>
                                <TZLabel time={issue.last_seen} className="border-dotted border-b text-xs" />
                            </div>
                        </div>
                    </Link>
                )
            })}
        </div>
    )
}

export default ErrorTrackingWidget
