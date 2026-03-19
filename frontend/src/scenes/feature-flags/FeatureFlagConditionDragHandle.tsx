import { DraggableSyntheticListeners } from '@dnd-kit/core'

import { SortableDragIcon } from 'lib/lemon-ui/icons'

interface FeatureFlagConditionDragHandleProps {
    listeners: DraggableSyntheticListeners | undefined
    hasMultipleConditions: boolean
}

const DragHandle = ({ listeners }: { listeners: DraggableSyntheticListeners | undefined }): JSX.Element => (
    <span
        className="FeatureFlagConditionDragHandle cursor-grab active:cursor-grabbing text-muted hover:text-default transition-colors"
        {...listeners}
        data-attr="feature-flag-condition-drag-handle"
    >
        <SortableDragIcon />
    </span>
)

export function FeatureFlagConditionDragHandle({
    listeners,
    hasMultipleConditions,
}: FeatureFlagConditionDragHandleProps): JSX.Element | null {
    if (!hasMultipleConditions) {
        return null
    }

    return <DragHandle listeners={listeners} />
}
