import { IconFlask, IconLive, IconMessage, IconRewindPlay, IconToggle, IconWarning } from '@posthog/icons'

import { DashboardWidgetType } from '~/types'

export interface WidgetTypeConfig {
    label: string
    description: string
    icon: JSX.Element
    color: string
}

export const WIDGET_TYPE_CONFIG: Record<DashboardWidgetType, WidgetTypeConfig> = {
    [DashboardWidgetType.Experiment]: {
        label: 'Experiment',
        description: 'Track results, ship winners, or stop underperformers',
        icon: <IconFlask />,
        color: 'var(--color-product-experiments-light)',
    },
    [DashboardWidgetType.Logs]: {
        label: 'Logs',
        description: 'Live log stream with severity and service filters',
        icon: <IconLive />,
        color: 'var(--color-product-logs-light)',
    },
    [DashboardWidgetType.ErrorTracking]: {
        label: 'Error tracking',
        description: 'Monitor errors and triage them inline',
        icon: <IconWarning />,
        color: 'var(--color-product-error-tracking-light)',
    },
    [DashboardWidgetType.SessionReplays]: {
        label: 'Session replays',
        description: 'See recent user sessions at a glance',
        icon: <IconRewindPlay />,
        color: 'var(--color-product-session-replay-light)',
    },
    [DashboardWidgetType.SurveyResponses]: {
        label: 'Surveys',
        description: 'View responses and control survey status',
        icon: <IconMessage />,
        color: 'var(--color-product-surveys-light)',
    },
    [DashboardWidgetType.FeatureFlag]: {
        label: 'Feature flag',
        description: 'Monitor rollout status and toggle flags inline',
        icon: <IconToggle />,
        color: 'var(--color-product-feature-flags-light)',
    },
}
