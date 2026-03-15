import { useEffect, useState } from 'react'

import { IconFlask } from '@posthog/icons'
import { LemonSkeleton, LemonTag } from '@posthog/lemon-ui'

import api from 'lib/api'
import { getSeriesColor } from 'lib/colors'
import { dayjs } from 'lib/dayjs'
import { LemonButton } from 'lib/lemon-ui/LemonButton'
import { LemonDialog } from 'lib/lemon-ui/LemonDialog'
import { lemonToast } from 'lib/lemon-ui/LemonToast/LemonToast'
import { Link } from 'lib/lemon-ui/Link'
import { humanFriendlyLargeNumber } from 'lib/utils'
import { urls } from 'scenes/urls'

import { performQuery } from '~/queries/query'
import { NodeKind } from '~/queries/schema/schema-general'

interface ExperimentWidgetProps {
    tileId: number
    config: Record<string, any>
    refreshKey?: number
}

interface ExperimentData {
    id: number
    name: string
    description: string
    start_date: string | null
    end_date: string | null
    feature_flag_key: string
    parameters: Record<string, any>
    metrics: any[]
    metrics_secondary: any[]
}

/** Normalized variant stats for display — works for both legacy and new formats. */
interface NormalizedVariant {
    key: string
    value: number
    samples: number
    chance_to_win?: number | null
    significant?: boolean | null
}

interface NormalizedMetricResult {
    baseline?: NormalizedVariant
    variants: NormalizedVariant[]
    probability?: Record<string, number>
}

const STATUS_COLORS: Record<string, string> = {
    complete: 'bg-success-highlight text-success',
    running: 'bg-warning-highlight text-warning',
    draft: 'bg-surface-secondary text-muted',
}

function getStatus(exp: ExperimentData): { label: string; colorClass: string } {
    if (exp.end_date) {
        return { label: 'Complete', colorClass: STATUS_COLORS.complete }
    }
    if (exp.start_date) {
        return { label: 'Running', colorClass: STATUS_COLORS.running }
    }
    return { label: 'Draft', colorClass: STATUS_COLORS.draft }
}

/** Normalize a query response into a consistent shape regardless of legacy/new format. */
function normalizeMetricResult(response: any): NormalizedMetricResult {
    // New format: has baseline + variant_results
    if (response.baseline && response.variant_results) {
        const baseline: NormalizedVariant = {
            key: response.baseline.key,
            value: response.baseline.sum ?? response.baseline.count ?? 0,
            samples: response.baseline.number_of_samples ?? response.baseline.absolute_exposure ?? 0,
        }
        const variants: NormalizedVariant[] = (response.variant_results || []).map((v: any) => ({
            key: v.key,
            value: v.sum ?? v.count ?? 0,
            samples: v.number_of_samples ?? v.absolute_exposure ?? 0,
            chance_to_win: v.chance_to_win ?? null,
            significant: v.significant ?? null,
        }))
        return { baseline, variants }
    }

    // Legacy format: has variants array + probability dict
    if (response.variants && Array.isArray(response.variants)) {
        const probability: Record<string, number> = response.probability || {}
        const allVariants: NormalizedVariant[] = response.variants.map((v: any) => {
            // Trends variant: { key, count, exposure, absolute_exposure }
            // Funnels variant: { key, success_count, failure_count }
            const isFunnels = 'success_count' in v
            return {
                key: v.key,
                value: isFunnels ? v.success_count : v.count,
                samples: isFunnels ? v.success_count + v.failure_count : (v.absolute_exposure ?? v.exposure ?? 0),
                chance_to_win: probability[v.key] ?? null,
                significant: response.significant ?? null,
            }
        })

        // First variant is typically the control/baseline
        const baseline = allVariants[0]
        const variants = allVariants.slice(1)
        return { baseline, variants, probability }
    }

    return { variants: [] }
}

function formatValue(variant: NormalizedVariant, samples: number): string {
    if (samples === 0) {
        return '—'
    }
    const rate = variant.value / samples
    if (isNaN(rate)) {
        return '—'
    }
    // If rate looks like a conversion rate (0-1 range), show as percentage
    if (rate <= 1 && rate >= 0) {
        return `${(rate * 100).toFixed(2)}%`
    }
    return humanFriendlyLargeNumber(rate)
}

function formatDelta(variant: NormalizedVariant, baseline: NormalizedVariant): string | null {
    if (!baseline || baseline.samples === 0 || variant.samples === 0) {
        return null
    }
    const baseRate = baseline.value / baseline.samples
    const varRate = variant.value / variant.samples
    if (baseRate === 0 || isNaN(baseRate) || isNaN(varRate)) {
        return null
    }
    const delta = ((varRate - baseRate) / baseRate) * 100
    return `${delta > 0 ? '+' : ''}${delta.toFixed(2)}%`
}

function MetricResultsTable({
    metricName,
    metricIndex,
    result,
}: {
    metricName: string
    metricIndex: number
    result: NormalizedMetricResult
}): JSX.Element {
    const allVariants = [...(result.baseline ? [result.baseline] : []), ...result.variants]

    if (allVariants.length === 0) {
        return (
            <div className="text-xs text-muted py-2 px-1">
                {metricIndex + 1}. {metricName || 'Metric'} — no data
            </div>
        )
    }

    // Determine if there is a significant winner among the variants
    const significantWinner = result.variants.find((v) => v.significant === true && (v.chance_to_win ?? 0) > 0.5)

    return (
        <div className="space-y-1">
            <div className="flex items-center gap-2 px-1">
                <span className="text-xs font-semibold text-text-primary">
                    {metricIndex + 1}. {metricName || 'Metric'}
                </span>
            </div>
            <div className="px-1">
                {significantWinner ? (
                    <span className="text-xs font-medium text-success bg-success-highlight px-1.5 py-0.5 rounded">
                        {significantWinner.key} is winning ({((significantWinner.chance_to_win ?? 0) * 100).toFixed(1)}
                        %)
                    </span>
                ) : (
                    <span className="text-xs text-muted">Not yet significant</span>
                )}
            </div>
            <table className="w-full text-xs">
                <thead>
                    <tr className="border-b border-border-light">
                        <th className="text-left font-medium text-muted py-1 px-1">Variant</th>
                        <th className="text-right font-medium text-muted py-1 px-1">Value</th>
                        <th className="text-right font-medium text-muted py-1 px-1">Delta</th>
                        <th className="text-right font-medium text-muted py-1 px-1">Win %</th>
                    </tr>
                </thead>
                <tbody>
                    {allVariants.map((v, i) => {
                        const isBaseline = result.baseline?.key === v.key
                        const delta = !isBaseline && result.baseline ? formatDelta(v, result.baseline) : null
                        const winPct = v.chance_to_win != null ? `${(v.chance_to_win * 100).toFixed(1)}%` : null
                        const deltaNum = delta ? parseFloat(delta) : 0

                        return (
                            <tr key={v.key} className="border-b border-border-light last:border-0">
                                <td className="py-1 px-1">
                                    <div className="flex items-center gap-1.5">
                                        <span
                                            className="inline-block h-2 w-2 rounded-full shrink-0"
                                            // eslint-disable-next-line react/forbid-dom-props
                                            style={{ backgroundColor: getSeriesColor(i) }}
                                        />
                                        <span className="font-medium">{v.key}</span>
                                    </div>
                                </td>
                                <td className="text-right py-1 px-1 tabular-nums">
                                    <div>{formatValue(v, v.samples)}</div>
                                    <div className="text-muted">
                                        {humanFriendlyLargeNumber(v.value)} / {v.samples.toLocaleString()}
                                    </div>
                                </td>
                                <td className="text-right py-1 px-1 tabular-nums">
                                    {delta ? (
                                        <span className={deltaNum < 0 ? 'text-danger' : 'text-success'}>{delta}</span>
                                    ) : (
                                        '—'
                                    )}
                                </td>
                                <td className="text-right py-1 px-1 tabular-nums">{winPct || '—'}</td>
                            </tr>
                        )
                    })}
                </tbody>
            </table>
        </div>
    )
}

function ExperimentWidget({ config, refreshKey }: ExperimentWidgetProps): JSX.Element {
    const [experiment, setExperiment] = useState<ExperimentData | null>(null)
    const [primaryResults, setPrimaryResults] = useState<NormalizedMetricResult[]>([])
    const [secondaryResults, setSecondaryResults] = useState<NormalizedMetricResult[]>([])
    const [loading, setLoading] = useState(true)
    const [resultsLoading, setResultsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [refreshCounter, setRefreshCounter] = useState(0)
    const [actionLoading, setActionLoading] = useState(false)

    const experimentId = config.experiment_id
    const showControls = config.show_controls !== false

    const handleShipVariant = (variantName: string): void => {
        LemonDialog.open({
            title: `Ship variant '${variantName}'?`,
            content: (
                <div className="text-sm text-secondary">
                    Ship variant '{variantName}' to 100% of users? This will end the experiment.
                </div>
            ),
            primaryButton: {
                children: `Ship ${variantName}`,
                type: 'primary',
                onClick: () => {
                    setActionLoading(true)
                    api.update(`api/projects/@current/experiments/${experimentId}`, {
                        end_date: new Date().toISOString(),
                    })
                        .then(() => {
                            lemonToast.success(`Variant '${variantName}' shipped successfully`)
                            setRefreshCounter((c) => c + 1)
                        })
                        .catch(() => {
                            lemonToast.error('Failed to ship variant')
                        })
                        .finally(() => {
                            setActionLoading(false)
                        })
                },
                size: 'small',
            },
            secondaryButton: {
                children: 'Cancel',
                type: 'tertiary',
                size: 'small',
            },
        })
    }

    const handleStopExperiment = (): void => {
        LemonDialog.open({
            title: 'Stop experiment?',
            content: (
                <div className="text-sm text-secondary">
                    Are you sure you want to stop this experiment? This action will end data collection.
                </div>
            ),
            primaryButton: {
                children: 'Stop experiment',
                type: 'primary',
                status: 'danger',
                onClick: () => {
                    setActionLoading(true)
                    api.update(`api/projects/@current/experiments/${experimentId}`, {
                        end_date: new Date().toISOString(),
                    })
                        .then(() => {
                            lemonToast.success('Experiment stopped')
                            setRefreshCounter((c) => c + 1)
                        })
                        .catch(() => {
                            lemonToast.error('Failed to stop experiment')
                        })
                        .finally(() => {
                            setActionLoading(false)
                        })
                },
                size: 'small',
            },
            secondaryButton: {
                children: 'Cancel',
                type: 'tertiary',
                size: 'small',
            },
        })
    }

    useEffect(() => {
        if (!experimentId) {
            setError('No experiment configured. Edit this widget to select one.')
            setLoading(false)
            return
        }

        setLoading(true)
        api.get(`api/projects/@current/experiments/${experimentId}`)
            .then(async (data: any) => {
                const exp = data as ExperimentData
                setExperiment(exp)
                setLoading(false)

                if (!exp.start_date) {
                    return
                }

                const allMetrics = [...(exp.metrics || []), ...(exp.metrics_secondary || [])]
                if (allMetrics.length === 0) {
                    return
                }

                setResultsLoading(true)

                const loadMetric = async (metric: any): Promise<NormalizedMetricResult | null> => {
                    try {
                        const query =
                            metric.kind === NodeKind.ExperimentMetric
                                ? { kind: NodeKind.ExperimentQuery, metric, experiment_id: experimentId }
                                : { ...metric, experiment_id: experimentId }
                        const response = await performQuery(query)
                        return normalizeMetricResult(response)
                    } catch {
                        return null
                    }
                }

                const primaryPromises = (exp.metrics || []).map(loadMetric)
                const secondaryPromises = (exp.metrics_secondary || []).map(loadMetric)

                const [primary, secondary] = await Promise.all([
                    Promise.all(primaryPromises),
                    Promise.all(secondaryPromises),
                ])

                setPrimaryResults(primary.filter(Boolean) as NormalizedMetricResult[])
                setSecondaryResults(secondary.filter(Boolean) as NormalizedMetricResult[])
                setResultsLoading(false)
            })
            .catch(() => {
                setError('Failed to load experiment')
                setLoading(false)
            })
    }, [experimentId, refreshKey, refreshCounter])

    if (loading) {
        return (
            <div className="p-4 space-y-3">
                <LemonSkeleton className="h-6 w-1/2" />
                <LemonSkeleton className="h-4 w-3/4" />
                <LemonSkeleton className="h-24 w-full" />
            </div>
        )
    }

    if (error || !experiment) {
        return (
            <div className="p-4 flex flex-col items-center justify-center h-full text-muted">
                <IconFlask className="text-3xl mb-2" />
                <span className="text-center">{error || 'Experiment not found'}</span>
                <LemonButton
                    type="secondary"
                    size="small"
                    className="mt-2"
                    onClick={() => {
                        setError(null)
                        setLoading(true)
                        setRefreshCounter((c) => c + 1)
                    }}
                >
                    Retry
                </LemonButton>
            </div>
        )
    }

    const status = getStatus(experiment)

    // Derive exposures from the first primary metric result
    const firstResult = primaryResults[0]
    const exposures = firstResult
        ? [...(firstResult.baseline ? [firstResult.baseline] : []), ...firstResult.variants]
        : []
    const totalExposures = exposures.reduce((acc, v) => acc + v.samples, 0)

    // Find a significant winning variant across all primary results for ship action
    const winningVariant = primaryResults
        .flatMap((r) => r.variants)
        .find((v) => v.significant === true && (v.chance_to_win ?? 0) > 0.5)

    const isRunning = experiment.start_date != null && experiment.end_date == null

    return (
        <div className="h-full overflow-auto">
            {/* Header */}
            <div className="px-3 pt-3 pb-2">
                <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-semibold text-sm mb-0 flex-1 truncate">
                        <Link to={urls.experiment(experimentId)} className="text-text-primary hover:underline">
                            {experiment.name}
                        </Link>
                    </h4>
                    <span className={`text-xs font-medium px-2 py-0.5 rounded shrink-0 ${status.colorClass}`}>
                        {status.label}
                    </span>
                </div>
                {experiment.start_date && (
                    <div className="text-xs text-muted">
                        {experiment.end_date
                            ? `${dayjs(experiment.start_date).format('MMM D, YYYY')} — ${dayjs(experiment.end_date).format('MMM D, YYYY')}`
                            : `Started ${dayjs(experiment.start_date).format('MMM D, YYYY')} (${dayjs(experiment.start_date).fromNow(true)})`}
                    </div>
                )}
            </div>

            {resultsLoading && (
                <div className="px-3 space-y-3 flex-1">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <div key={i} className="space-y-1">
                            <LemonSkeleton className="h-4 w-1/3" />
                            <LemonSkeleton className="h-16 w-full" />
                        </div>
                    ))}
                </div>
            )}

            {!resultsLoading && experiment.start_date && (
                <div className="px-3 space-y-3">
                    {/* Exposures bar */}
                    {totalExposures > 0 && (
                        <div className="flex items-center gap-2 text-xs">
                            <span className="font-semibold text-muted uppercase">Exposures</span>
                            <span className="font-semibold">{totalExposures.toLocaleString()}</span>
                            <div className="flex-1 flex h-1.5 rounded-full overflow-hidden bg-surface-secondary">
                                {exposures.map((v, i) => (
                                    <div
                                        key={v.key}
                                        className="h-full"
                                        // eslint-disable-next-line react/forbid-dom-props
                                        style={{
                                            width: `${(v.samples / totalExposures) * 100}%`,
                                            backgroundColor: getSeriesColor(i),
                                        }}
                                    />
                                ))}
                            </div>
                            {exposures.map((v, i) => (
                                <span key={v.key} className="flex items-center gap-1 text-muted">
                                    <span
                                        className="inline-block h-2 w-2 rounded-full"
                                        // eslint-disable-next-line react/forbid-dom-props
                                        style={{ backgroundColor: getSeriesColor(i) }}
                                    />
                                    {v.key} {((v.samples / totalExposures) * 100).toFixed(1)}%
                                </span>
                            ))}
                        </div>
                    )}

                    {/* Primary metrics */}
                    {primaryResults.length > 0 && (
                        <div className="space-y-3">
                            <div className="text-xs font-semibold text-muted uppercase">Primary metrics</div>
                            {primaryResults.map((result, i) => (
                                <MetricResultsTable
                                    key={i}
                                    metricName={experiment.metrics[i]?.name}
                                    metricIndex={i}
                                    result={result}
                                />
                            ))}
                        </div>
                    )}

                    {/* Secondary metrics */}
                    {secondaryResults.length > 0 && (
                        <div className="space-y-3">
                            <div className="text-xs font-semibold text-muted uppercase">Secondary metrics</div>
                            {secondaryResults.map((result, i) => (
                                <MetricResultsTable
                                    key={i}
                                    metricName={experiment.metrics_secondary[i]?.name}
                                    metricIndex={i}
                                    result={result}
                                />
                            ))}
                        </div>
                    )}

                    {primaryResults.length === 0 && secondaryResults.length === 0 && (
                        <div className="flex items-center justify-center text-muted text-sm py-4">
                            No results available yet
                        </div>
                    )}
                </div>
            )}

            {!experiment.start_date && (
                <div className="flex items-center justify-center text-muted text-sm py-4">
                    <LemonTag type="muted">Draft — not started yet</LemonTag>
                </div>
            )}

            {/* Action controls */}
            {showControls && isRunning && (
                <div className="px-3 py-2 space-y-2">
                    <div className="border-t border-border-light pt-2" />
                    {winningVariant && (
                        <LemonButton
                            type="primary"
                            status="default"
                            size="small"
                            fullWidth
                            center
                            loading={actionLoading}
                            onClick={() => handleShipVariant(winningVariant.key)}
                        >
                            Ship {winningVariant.key}
                        </LemonButton>
                    )}
                    <LemonButton
                        type="secondary"
                        status="danger"
                        size="small"
                        fullWidth
                        center
                        loading={actionLoading}
                        onClick={handleStopExperiment}
                    >
                        Stop experiment
                    </LemonButton>
                </div>
            )}
        </div>
    )
}

export default ExperimentWidget
