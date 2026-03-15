import clsx from 'clsx'
import React from 'react'

import { IconExternal } from '@posthog/icons'

import { CardMeta, Resizeable } from 'lib/components/Cards/CardMeta'
import { DashboardResizeHandles } from 'lib/components/Cards/handles'
import { EditModeEdgeOverlay } from 'lib/components/Cards/InsightCard/EditModeEdgeOverlay'
import { LemonButton } from 'lib/lemon-ui/LemonButton'
import { MoreProps } from 'lib/lemon-ui/LemonButton/More'
import { WIDGET_TYPE_CONFIG } from 'scenes/dashboard/widgets/widgetTypes'

import { DashboardPlacement, DashboardWidgetModel } from '~/types'

export interface WidgetCardProps extends React.HTMLAttributes<HTMLDivElement>, Resizeable {
    widget: DashboardWidgetModel
    placement: DashboardPlacement
    children?: React.ReactNode
    canEnterEditModeFromEdge?: boolean
    onEnterEditModeFromEdge?: () => void
    moreButtonOverlay?: MoreProps['overlay']
    onDragHandleMouseDown?: React.MouseEventHandler<HTMLDivElement>
    openUrl?: string
    contentRenderer: React.ReactNode
    /** Time range label for list widgets (logs, errors, replays) */
    dateLabel?: string | null
    /** Entity name for detail widgets (flag key, experiment name, survey name) */
    entityName?: string | null
}

function WidgetCardInternal(
    {
        widget,
        showResizeHandles,
        children,
        className,
        moreButtonOverlay,
        placement,
        canEnterEditModeFromEdge,
        onEnterEditModeFromEdge,
        onDragHandleMouseDown,
        openUrl,
        contentRenderer,
        dateLabel,
        entityName,
        ...divProps
    }: WidgetCardProps,
    ref: React.Ref<HTMLDivElement>
): JSX.Element {
    const shouldHideMoreButton = placement === DashboardPlacement.Public
    const typeConfig = WIDGET_TYPE_CONFIG[widget.widget_type]

    return (
        <div
            className={clsx('WidgetCard InsightCard border rounded flex flex-col', className)}
            data-attr="widget-card"
            {...divProps}
            ref={ref}
        >
            <CardMeta
                showEditingControls={!shouldHideMoreButton && !!moreButtonOverlay}
                showDetailsControls={false}
                topHeading={
                    <span className="flex items-center gap-1.5">
                        <span
                            className="inline-flex items-center justify-center"
                            // eslint-disable-next-line react/forbid-dom-props
                            style={{ color: typeConfig.color }}
                        >
                            {typeConfig.icon}
                        </span>
                        {typeConfig.label}
                        {dateLabel && (
                            <>
                                <span className="text-muted">•</span>
                                <span className="whitespace-nowrap">{dateLabel}</span>
                            </>
                        )}
                    </span>
                }
                content={entityName ? <span className="font-semibold text-sm truncate block">{entityName}</span> : null}
                metaDetails={null}
                moreButtons={moreButtonOverlay}
                onMouseDown={onDragHandleMouseDown}
                extraControls={
                    openUrl ? (
                        <LemonButton
                            size="small"
                            type="tertiary"
                            icon={<IconExternal />}
                            to={openUrl}
                            targetBlank
                            tooltip="Open full view"
                        />
                    ) : null
                }
            />

            <div className="flex-1 overflow-auto min-h-0">{contentRenderer}</div>

            {canEnterEditModeFromEdge && !showResizeHandles && onEnterEditModeFromEdge && (
                <EditModeEdgeOverlay onEnterEditMode={onEnterEditModeFromEdge} />
            )}
            {showResizeHandles && <DashboardResizeHandles />}
            {children}
        </div>
    )
}

export const WidgetCard = React.forwardRef<HTMLDivElement, WidgetCardProps>(WidgetCardInternal)
