import { IconBolt, IconLlmAnalytics, IconReceipt, IconTarget } from '@posthog/icons'
import { LemonButton } from '@posthog/lemon-ui'

import { cn } from 'lib/utils/css-classes'
import { urls } from 'scenes/urls'

import { ProductKey } from '~/queries/schema/schema-general'
import { OnboardingStepKey } from '~/types'

export type LLMAnalyticsEmptyStateVideoPayload = {
    videoUrl?: string
    posterUrl?: string
}

export interface LLMAnalyticsEmptyStatePageProps {
    className?: string
    video?: LLMAnalyticsEmptyStateVideoPayload
}

export function LLMAnalyticsEmptyStatePage({ className, video }: LLMAnalyticsEmptyStatePageProps): JSX.Element {
    return (
        <div className={cn('flex flex-col items-center justify-center max-w-4xl mx-auto py-12 px-6', className)}>
            <div className="flex items-center gap-3 mb-6">
                <IconLlmAnalytics className="w-8 h-8 shrink-0 text-[var(--color-product-llm-analytics-light)]" />
                <h1 className="text-2xl font-bold m-0">LLM analytics</h1>
            </div>

            <p className="text-center text-muted mb-8 max-w-xl">
                Understand costs, latency, and output quality across every model call your app makes.
            </p>

            <div className="w-full max-w-3xl rounded-lg overflow-hidden border border-border bg-bg-light mb-8 shadow-sm">
                {video?.videoUrl ? (
                    <video
                        src={video.videoUrl}
                        controls
                        autoPlay
                        muted
                        loop
                        playsInline
                        preload="metadata"
                        poster={video.posterUrl}
                        className="w-full aspect-video"
                    />
                ) : (
                    <div className="w-full aspect-video flex flex-col items-center justify-center gap-2 p-8">
                        <p className="text-sm text-muted m-0">Demo video loads when enabled for this experiment.</p>
                        <p className="text-xs text-muted-alt m-0">
                            (Set a feature flag payload with a `videoUrl` to show the tour.)
                        </p>
                    </div>
                )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 w-full max-w-3xl mb-8">
                <div className="border border-border rounded-lg p-4">
                    <div className="flex items-center gap-2 font-semibold mb-1">
                        <IconReceipt className="w-5 h-5 text-muted" />
                        Costs and usage
                    </div>
                    <div className="text-sm text-muted">See spend by model, provider, and prompt.</div>
                </div>
                <div className="border border-border rounded-lg p-4">
                    <div className="flex items-center gap-2 font-semibold mb-1">
                        <IconBolt className="w-5 h-5 text-muted" />
                        Latency and reliability
                    </div>
                    <div className="text-sm text-muted">Track performance over time and catch errors fast.</div>
                </div>
                <div className="border border-border rounded-lg p-4">
                    <div className="flex items-center gap-2 font-semibold mb-1">
                        <IconTarget className="w-5 h-5 text-muted" />
                        Quality and evaluations
                    </div>
                    <div className="text-sm text-muted">Measure output quality and compare prompt changes.</div>
                </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 mb-6">
                <LemonButton
                    type="primary"
                    size="large"
                    to={urls.onboarding({
                        productKey: ProductKey.LLM_ANALYTICS,
                        stepKey: OnboardingStepKey.INSTALL,
                    })}
                    data-attr="llma-empty-state-setup-cta"
                >
                    Set up LLM analytics
                </LemonButton>
                <LemonButton
                    type="secondary"
                    size="large"
                    to="https://posthog.com/docs/llm-analytics"
                    targetBlank
                    data-attr="llma-empty-state-docs-cta"
                >
                    Read the docs
                </LemonButton>
            </div>

            <p className="text-xs text-muted">Used by 55K+ teams</p>
        </div>
    )
}
