import { useActions } from 'kea'
import React, { useState } from 'react'

import { WidgetCard } from 'lib/components/Cards/WidgetCard/WidgetCard'
import { LemonButton } from 'lib/lemon-ui/LemonButton'
import { LemonDialog } from 'lib/lemon-ui/LemonDialog'
import { LemonDivider } from 'lib/lemon-ui/LemonDivider'
import { LemonMenu } from 'lib/lemon-ui/LemonMenu'
import { urls } from 'scenes/urls'

import type {
    DashboardPlacement,
    DashboardTile,
    DashboardType,
    DashboardWidgetModel,
    DashboardWidgetType,
    QueryBasedInsightModel,
} from '~/types'

import { dashboardLogic } from '../dashboardLogic'
import { EditWidgetModal } from '../widgets/EditWidgetModal'
import { useWidgetDateLabel, useWidgetEntityName, WidgetRenderer } from '../widgets/WidgetRenderer'

type BaseWidgetCardProps = React.ComponentProps<typeof WidgetCard>

interface DashboardWidgetItemProps extends Omit<
    BaseWidgetCardProps,
    'widget' | 'placement' | 'moreButtonOverlay' | 'openUrl' | 'contentRenderer'
> {
    tile: DashboardTile<QueryBasedInsightModel>
    widget: DashboardWidgetModel
    placement: DashboardPlacement
    otherDashboards: Pick<DashboardType, 'id' | 'name'>[]
    moveToDashboard?: (target: Pick<DashboardType, 'id' | 'name'>) => void
    removeFromDashboard?: () => void
    showEditingControls?: boolean
}

function getWidgetOpenUrl(widgetType: DashboardWidgetType, config: Record<string, any>): string | undefined {
    switch (widgetType) {
        case 'experiment':
            return config.experiment_id ? urls.experiment(config.experiment_id) : undefined
        case 'logs':
            return urls.logs()
        case 'error_tracking':
            return urls.errorTracking()
        case 'session_replays':
            return urls.replay()
        case 'survey_responses':
            return config.survey_id ? urls.survey(config.survey_id) : undefined
        default:
            return undefined
    }
}

function DashboardWidgetItemInternal(
    {
        tile,
        widget,
        placement,
        otherDashboards,
        moveToDashboard,
        removeFromDashboard,
        ...widgetCardProps
    }: DashboardWidgetItemProps,
    ref: React.ForwardedRef<HTMLDivElement>
): JSX.Element {
    const { updateWidgetConfig } = useActions(dashboardLogic)
    const [editModalOpen, setEditModalOpen] = useState(false)
    const openUrl = getWidgetOpenUrl(widget.widget_type, widget.config)
    const dateLabel = useWidgetDateLabel(widget)
    const entityName = useWidgetEntityName(widget)

    return (
        <>
            <WidgetCard
                ref={ref}
                widget={widget}
                placement={placement}
                openUrl={openUrl}
                dateLabel={dateLabel}
                entityName={entityName}
                contentRenderer={<WidgetRenderer tileId={tile.id} widget={widget} />}
                {...widgetCardProps}
                moreButtonOverlay={
                    <>
                        <LemonButton fullWidth onClick={() => setEditModalOpen(true)}>
                            Edit
                        </LemonButton>
                        {moveToDashboard && (
                            <LemonMenu
                                placement="right-start"
                                fallbackPlacements={['left-start']}
                                closeParentPopoverOnClickInside
                                items={
                                    otherDashboards.length
                                        ? otherDashboards.map((otherDashboard) => ({
                                              label: otherDashboard.name || <i>Untitled</i>,
                                              onClick: () => moveToDashboard(otherDashboard),
                                          }))
                                        : [
                                              {
                                                  label: 'No other dashboards',
                                                  disabledReason: 'No other dashboards',
                                              },
                                          ]
                                }
                            >
                                <LemonButton
                                    fullWidth
                                    disabledReason={otherDashboards.length ? undefined : 'No other dashboards'}
                                >
                                    Move to
                                </LemonButton>
                            </LemonMenu>
                        )}
                        <LemonDivider />
                        {removeFromDashboard && (
                            <LemonButton
                                status="danger"
                                onClick={() =>
                                    LemonDialog.open({
                                        title: 'Remove widget from dashboard',
                                        description: 'Are you sure you want to remove this widget from the dashboard?',
                                        primaryButton: {
                                            children: 'Remove from dashboard',
                                            status: 'danger',
                                            onClick: () => removeFromDashboard(),
                                        },
                                        secondaryButton: {
                                            children: 'Cancel',
                                        },
                                    })
                                }
                                fullWidth
                                data-attr="remove-widget-tile-from-dashboard"
                            >
                                Remove from dashboard
                            </LemonButton>
                        )}
                    </>
                }
            />
            <EditWidgetModal
                isOpen={editModalOpen}
                onClose={() => setEditModalOpen(false)}
                widget={widget}
                onSave={(config) => updateWidgetConfig(tile.id, widget.id, config)}
            />
        </>
    )
}

export const DashboardWidgetItem = React.forwardRef<HTMLDivElement, DashboardWidgetItemProps>(
    DashboardWidgetItemInternal
) as typeof DashboardWidgetItemInternal
