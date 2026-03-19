import { useValues } from 'kea'

import { Link } from '@posthog/lemon-ui'

import { urls } from 'scenes/urls'

import { EvaluationConfig, LLM_PROVIDER_LABELS, LLMProvider, llmProviderKeysLogic } from './llmProviderKeysLogic'

export function TrialUsageMeter({ showSettingsLink = false }: { showSettingsLink?: boolean }): JSX.Element | null {
    const { evaluationConfig } = useValues(llmProviderKeysLogic)

    if (!evaluationConfig || !evaluationConfig.trial_providers?.length) {
        return null
    }

    return <TrialUsageMeterDisplay evaluationConfig={evaluationConfig} showSettingsLink={showSettingsLink} />
}

function formatProviderNames(providers: LLMProvider[]): string {
    const names = providers.map((p) => LLM_PROVIDER_LABELS[p])
    if (names.length === 1) {
        return names[0]
    }
    return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

export function TrialUsageMeterDisplay({
    evaluationConfig,
    showSettingsLink = false,
}: {
    evaluationConfig: EvaluationConfig
    showSettingsLink?: boolean
}): JSX.Element {
    const { trial_eval_limit, trial_evals_remaining, trial_providers } = evaluationConfig
    const percentUsed = Math.min(((trial_eval_limit - trial_evals_remaining) / trial_eval_limit) * 100, 100)
    const isExhausted = trial_evals_remaining <= 0
    const providerLabel = formatProviderNames(trial_providers)

    const addKeyLink = showSettingsLink ? (
        <Link to={urls.settings('environment-llm-analytics', 'llm-analytics-byok')}>
            Add your {providerLabel} API {trial_providers.length === 1 ? 'key' : 'keys'}
        </Link>
    ) : (
        `Add your ${providerLabel} API ${trial_providers.length === 1 ? 'key' : 'keys'}`
    )

    return (
        <div className="rounded-lg p-4 space-y-3 border">
            <div className="flex justify-between items-center">
                <span className="font-medium">Trial evaluations</span>
                <span className={`text-sm ${isExhausted ? 'font-medium' : 'text-muted'}`}>
                    {trial_evals_remaining} of {trial_eval_limit} remaining
                </span>
            </div>
            <div className="h-2 bg-border rounded-full overflow-hidden">
                <div
                    className={`h-full transition-all ${isExhausted ? 'bg-danger' : 'bg-success'}`}
                    // eslint-disable-next-line react/forbid-dom-props
                    style={{ width: `${percentUsed}%` }}
                />
            </div>
            {isExhausted ? (
                <p className="text-sm">Trial evaluations exhausted. {addKeyLink} to continue running evaluations.</p>
            ) : (
                <p className="text-sm text-muted">
                    Your {providerLabel} evaluations are using the trial.{' '}
                    {showSettingsLink ? (
                        <Link to={urls.settings('environment-llm-analytics', 'llm-analytics-byok')}>
                            Add your own {trial_providers.length === 1 ? 'key' : 'keys'}
                        </Link>
                    ) : (
                        `Add your own ${trial_providers.length === 1 ? 'key' : 'keys'}`
                    )}{' '}
                    to avoid hitting the {trial_eval_limit} evaluation limit.
                </p>
            )}
        </div>
    )
}
