import { useValues } from 'kea'
import { Suspense, lazy, useEffect, useMemo, useState } from 'react'

import { IconWarning } from '@posthog/icons'

import api from 'lib/api'
import { LemonSkeleton } from 'lib/lemon-ui/LemonSkeleton'
import { dateFilterToText } from 'lib/utils'

import { ErrorBoundary } from '~/layout/ErrorBoundary'
import { DashboardWidgetModel, DashboardWidgetType } from '~/types'

import { dashboardLogic } from '../dashboardLogic'

const ExperimentWidget = lazy(() => import('./ExperimentWidget'))
const LogsWidget = lazy(() => import('./LogsWidget'))
const ErrorTrackingWidget = lazy(() => import('./ErrorTrackingWidget'))
const SessionReplaysWidget = lazy(() => import('./SessionReplaysWidget'))
const SurveyResponsesWidget = lazy(() => import('./SurveyResponsesWidget'))
const FeatureFlagWidget = lazy(() => import('./FeatureFlagWidget'))

interface WidgetRendererProps {
    tileId: number
    widget: DashboardWidgetModel
}

/** Get the widget's own date_from/date_to from its config, per widget type. */
function getWidgetDateRange(widget: DashboardWidgetModel): { date_from?: string; date_to?: string } {
    const config = widget.config as Record<string, any>
    switch (widget.widget_type) {
        case DashboardWidgetType.Logs:
            return { date_from: config.filters?.dateFrom || '-24h' }
        case DashboardWidgetType.SessionReplays:
            return { date_from: config.date_from || '-7d', date_to: config.date_to }
        case DashboardWidgetType.ErrorTracking:
            return { date_from: '-7d' }
        case DashboardWidgetType.SurveyResponses:
            return { date_from: '-30d' }
        default:
            return {}
    }
}

function WidgetFallback(): JSX.Element {
    return (
        <div className="p-4 space-y-2">
            <LemonSkeleton className="h-4 w-3/4" />
            <LemonSkeleton className="h-4 w-1/2" />
            <LemonSkeleton className="h-32 w-full" />
        </div>
    )
}

function UnknownWidgetType({ widgetType }: { widgetType: string }): JSX.Element {
    return (
        <div className="p-4 flex flex-col items-center justify-center h-full text-muted">
            <IconWarning className="text-3xl mb-2" />
            <span className="text-sm">Unknown widget type: {widgetType}</span>
        </div>
    )
}

export function WidgetRenderer({ tileId, widget }: WidgetRendererProps): JSX.Element {
    const { widgetRefreshKey, effectiveEditBarFilters } = useValues(dashboardLogic)
    const { widget_type, config } = widget

    // Compute effective dates: dashboard override takes precedence over widget config
    const dashboardDateFrom = effectiveEditBarFilters?.date_from
    const dashboardDateTo = effectiveEditBarFilters?.date_to

    const widgetDates = getWidgetDateRange(widget)
    const effectiveDateFrom = dashboardDateFrom || widgetDates.date_from
    const effectiveDateTo = dashboardDateTo || widgetDates.date_to

    const widgetContent = (() => {
        switch (widget_type) {
            case DashboardWidgetType.Experiment:
                return <ExperimentWidget tileId={tileId} config={config} refreshKey={widgetRefreshKey} />
            case DashboardWidgetType.Logs:
                return (
                    <LogsWidget
                        tileId={tileId}
                        config={config}
                        refreshKey={widgetRefreshKey}
                        effectiveDateFrom={effectiveDateFrom}
                        effectiveDateTo={effectiveDateTo}
                    />
                )
            case DashboardWidgetType.ErrorTracking:
                return (
                    <ErrorTrackingWidget
                        tileId={tileId}
                        config={config}
                        refreshKey={widgetRefreshKey}
                        effectiveDateFrom={effectiveDateFrom}
                        effectiveDateTo={effectiveDateTo}
                    />
                )
            case DashboardWidgetType.SessionReplays:
                return (
                    <SessionReplaysWidget
                        tileId={tileId}
                        config={config}
                        refreshKey={widgetRefreshKey}
                        effectiveDateFrom={effectiveDateFrom}
                        effectiveDateTo={effectiveDateTo}
                    />
                )
            case DashboardWidgetType.SurveyResponses:
                return (
                    <SurveyResponsesWidget
                        tileId={tileId}
                        config={config}
                        refreshKey={widgetRefreshKey}
                        effectiveDateFrom={effectiveDateFrom}
                        effectiveDateTo={effectiveDateTo}
                    />
                )
            case DashboardWidgetType.FeatureFlag:
                return <FeatureFlagWidget tileId={tileId} config={config} refreshKey={widgetRefreshKey} />
            default:
                return <UnknownWidgetType widgetType={widget_type} />
        }
    })()

    return (
        <ErrorBoundary>
            <Suspense fallback={<WidgetFallback />}>{widgetContent}</Suspense>
        </ErrorBoundary>
    )
}

/** Exposed for DashboardWidgetItem to pass to WidgetCard. */
export function useWidgetDateLabel(widget: DashboardWidgetModel): string | null {
    const { effectiveEditBarFilters } = useValues(dashboardLogic)

    return useMemo(() => {
        // Detail widgets (single entity) don't show a time range — only list widgets do
        const listWidgets = [
            DashboardWidgetType.Logs,
            DashboardWidgetType.ErrorTracking,
            DashboardWidgetType.SessionReplays,
        ]
        if (!listWidgets.includes(widget.widget_type)) {
            return null
        }
        const dashboardDateFrom = effectiveEditBarFilters?.date_from
        const dashboardDateTo = effectiveEditBarFilters?.date_to
        const widgetDates = getWidgetDateRange(widget)
        const from = dashboardDateFrom || widgetDates.date_from
        const to = dashboardDateTo || widgetDates.date_to
        return dateFilterToText(from, to, null)
    }, [widget, effectiveEditBarFilters])
}

/** Fetches the entity name for detail widgets (flag, experiment, survey). */
export function useWidgetEntityName(widget: DashboardWidgetModel): string | null {
    const [name, setName] = useState<string | null>(null)
    const config = widget.config as Record<string, any>

    const endpoint = useMemo(() => {
        switch (widget.widget_type) {
            case DashboardWidgetType.FeatureFlag:
                return config.feature_flag_id ? `api/projects/@current/feature_flags/${config.feature_flag_id}` : null
            case DashboardWidgetType.Experiment:
                return config.experiment_id ? `api/projects/@current/experiments/${config.experiment_id}` : null
            case DashboardWidgetType.SurveyResponses:
                return config.survey_id ? `api/projects/@current/surveys/${config.survey_id}` : null
            default:
                return null
        }
    }, [widget.widget_type, config.feature_flag_id, config.experiment_id, config.survey_id])

    useEffect(() => {
        if (!endpoint) {
            setName(null)
            return
        }
        api.get(endpoint)
            .then((data: any) => setName(data.key || data.name || null))
            .catch(() => setName(null))
    }, [endpoint])

    return name
}
