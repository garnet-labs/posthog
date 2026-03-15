import { useCallback, useEffect, useState } from 'react'

import { IconFlag } from '@posthog/icons'
import { LemonSkeleton, LemonSwitch, LemonTag } from '@posthog/lemon-ui'

import api from 'lib/api'
import { TZLabel } from 'lib/components/TZLabel'
import { LemonButton } from 'lib/lemon-ui/LemonButton'
import { LemonDialog } from 'lib/lemon-ui/LemonDialog'
import { LemonProgress } from 'lib/lemon-ui/LemonProgress'
import { lemonToast } from 'lib/lemon-ui/LemonToast/LemonToast'
import { Tooltip } from 'lib/lemon-ui/Tooltip'

interface FeatureFlagWidgetProps {
    tileId: number
    config: Record<string, any> // { feature_flag_id?: number, mode?: 'data' | 'actions' | 'both' }
    refreshKey?: number
}

interface FeatureFlagData {
    id: number
    key: string
    name: string
    active: boolean
    created_at: string
    updated_at: string
    created_by: { first_name: string; email: string } | null
    filters: {
        groups?: Array<{
            rollout_percentage?: number | null
            properties?: Array<{ key: string; value: any; operator: string; type: string }>
        }>
        multivariate?: {
            variants: Array<{ key: string; name?: string; rollout_percentage: number }>
        } | null
    }
    experiment_set?: number[]
    surveys_linked_flag?: any[]
}

const REFRESH_INTERVAL_MS = 60_000

function getEffectiveRollout(flag: FeatureFlagData): number | null {
    if (!flag.filters?.groups?.length) {
        return null
    }
    if (flag.filters.groups.length === 1) {
        return flag.filters.groups[0].rollout_percentage ?? null
    }
    const pcts = flag.filters.groups.map((g) => g.rollout_percentage).filter((p): p is number => p != null)
    return pcts.length > 0 ? Math.max(...pcts) : null
}

function RolloutBar({ percentage }: { percentage: number }): JSX.Element {
    return (
        <div className="flex items-center gap-2">
            <LemonProgress percent={percentage} className="flex-1" />
            <span className="text-sm font-medium tabular-nums shrink-0">{percentage}%</span>
        </div>
    )
}

function ReleaseConditions({ flag }: { flag: FeatureFlagData }): JSX.Element {
    const groups = flag.filters?.groups || []
    if (groups.length === 0) {
        return <span className="text-xs text-muted">No release conditions</span>
    }

    return (
        <div className="space-y-1">
            {groups.map((group, i) => {
                const props = group.properties || []
                const rollout = group.rollout_percentage
                return (
                    <div key={i} className="text-xs text-muted flex items-center gap-1.5">
                        <span className="font-medium text-text-secondary">Set {i + 1}:</span>
                        {props.length > 0 ? (
                            <span>
                                {props.length} condition{props.length !== 1 ? 's' : ''}
                            </span>
                        ) : (
                            <span>All users</span>
                        )}
                        {rollout != null && <span>at {rollout}%</span>}
                    </div>
                )
            })}
        </div>
    )
}

function Variants({ flag }: { flag: FeatureFlagData }): JSX.Element | null {
    const variants = flag.filters?.multivariate?.variants
    if (!variants?.length) {
        return null
    }

    return (
        <div className="space-y-1.5">
            <div className="text-xs font-semibold text-muted uppercase">Variants</div>
            {variants.map((v) => (
                <div key={v.key} className="flex items-center gap-2 text-sm">
                    <span className="font-medium flex-1 truncate">{v.key}</span>
                    {v.name && <span className="text-xs text-muted truncate">{v.name}</span>}
                    <span className="text-xs tabular-nums text-muted shrink-0">{v.rollout_percentage}%</span>
                </div>
            ))}
        </div>
    )
}

function FeatureFlagWidget({ config, refreshKey }: FeatureFlagWidgetProps): JSX.Element {
    const [flag, setFlag] = useState<FeatureFlagData | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [toggling, setToggling] = useState(false)

    const flagId = config.feature_flag_id
    const showControls = config.show_controls !== false

    const fetchFlag = useCallback(() => {
        if (!flagId) {
            setError('No feature flag configured. Edit this widget to select one.')
            setLoading(false)
            return
        }

        api.get(`api/projects/@current/feature_flags/${flagId}`)
            .then((data: any) => {
                setFlag(data as FeatureFlagData)
                setLoading(false)
                setError(null)
            })
            .catch((e: any) => {
                setError(e?.status === 404 ? 'Feature flag was deleted.' : 'Failed to load feature flag')
                setLoading(false)
            })
    }, [flagId])

    useEffect(() => {
        setLoading(true)
        fetchFlag()
        const interval = setInterval(fetchFlag, REFRESH_INTERVAL_MS)
        return () => clearInterval(interval)
    }, [fetchFlag, refreshKey])

    const handleToggle = useCallback(
        (newActive: boolean): void => {
            if (!flag) {
                return
            }

            const doToggle = (): void => {
                setToggling(true)
                api.update(`api/projects/@current/feature_flags/${flag.id}`, { active: newActive })
                    .then(() => {
                        setFlag((prev) => (prev ? { ...prev, active: newActive } : prev))
                        setToggling(false)
                        lemonToast.success(`Flag "${flag.key}" ${newActive ? 'enabled' : 'disabled'}`)
                        setTimeout(fetchFlag, 1000)
                    })
                    .catch(() => {
                        setToggling(false)
                        lemonToast.error(`Failed to ${newActive ? 'enable' : 'disable'} flag`)
                    })
            }

            if (flag.active && !newActive) {
                LemonDialog.open({
                    title: 'Disable this flag?',
                    description: `This will immediately stop serving "${flag.key}" to all matched users.`,
                    primaryButton: { children: 'Disable', status: 'danger', onClick: doToggle },
                    secondaryButton: { children: 'Cancel' },
                })
            } else {
                doToggle()
            }
        },
        [flag, fetchFlag]
    )

    if (loading) {
        return (
            <div className="p-4 space-y-3">
                <LemonSkeleton className="h-5 w-1/2" />
                <LemonSkeleton className="h-3 w-3/4" />
                <LemonSkeleton className="h-8 w-full" />
                <LemonSkeleton className="h-20 w-full" />
            </div>
        )
    }

    if (error || !flag) {
        return (
            <div className="p-4 flex flex-col items-center justify-center h-full text-muted gap-2">
                <IconFlag className="text-3xl" />
                <span className="text-center text-sm">{error || 'Flag not found'}</span>
                <LemonButton
                    type="secondary"
                    size="small"
                    onClick={() => {
                        setError(null)
                        setLoading(true)
                        fetchFlag()
                    }}
                >
                    Retry
                </LemonButton>
            </div>
        )
    }

    const rollout = getEffectiveRollout(flag)
    const hasExperiments = (flag.experiment_set?.length || 0) > 0

    return (
        <div className="h-full overflow-auto">
            {/* Toggle control */}
            <div className="px-3 py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <LemonTag type={flag.active ? 'success' : 'default'} size="small">
                        {flag.active ? 'Enabled' : 'Disabled'}
                    </LemonTag>
                    <span className="text-xs text-muted">
                        Updated <TZLabel time={flag.updated_at} className="text-xs" />
                    </span>
                </div>
                {showControls && (
                    <LemonSwitch checked={flag.active} onChange={handleToggle} loading={toggling} bordered />
                )}
            </div>
            {hasExperiments && (
                <Tooltip title="This flag is linked to an experiment. Toggling it may affect experiment results.">
                    <div className="text-xs text-warning px-3 pb-2">
                        Linked to {flag.experiment_set!.length} experiment(s)
                    </div>
                </Tooltip>
            )}

            {/* Data: Rollout */}
            {rollout != null && (
                <div className="px-3 py-2 border-t border-border-light">
                    <div className="text-xs font-semibold text-muted uppercase mb-1.5">Rollout</div>
                    <RolloutBar percentage={rollout} />
                </div>
            )}

            {/* Data: Variants */}
            {flag.filters?.multivariate?.variants && (
                <div className="px-3 py-2 border-t border-border-light">
                    <Variants flag={flag} />
                </div>
            )}

            {/* Release conditions */}
            <div className="px-3 py-2 border-t border-border-light">
                <div className="text-xs font-semibold text-muted uppercase mb-1.5">Release conditions</div>
                <ReleaseConditions flag={flag} />
            </div>
        </div>
    )
}

export default FeatureFlagWidget
