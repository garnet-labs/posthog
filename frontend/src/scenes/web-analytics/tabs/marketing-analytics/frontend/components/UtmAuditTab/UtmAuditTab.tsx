import { LemonBanner } from '@posthog/lemon-ui'

export function UtmAuditTab(): JSX.Element {
    return (
        <div className="mt-4">
            <LemonBanner type="info">
                UTM audit is coming soon. This tab will help you identify campaigns with missing or misconfigured UTM
                parameters and fix them directly from PostHog.
            </LemonBanner>
        </div>
    )
}
