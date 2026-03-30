import { IconGraph } from '@posthog/icons'

import { ErrorTrackingRuntime } from 'lib/components/Errors/types'

import { RuntimeIcon } from 'products/error_tracking/frontend/components/RuntimeIcon'

import { ItemRenderer, TimelineItem } from '..'
import { BasePreview } from './base'

export interface CustomItem extends TimelineItem {
    payload: {
        name: string
        runtime: ErrorTrackingRuntime
    }
}

export const customItemRenderer: ItemRenderer<CustomItem> = {
    sourceIcon: ({ item }) => <RuntimeIcon runtime={item.payload.runtime} />,
    categoryIcon: <IconGraph />,
    render: ({ item }): JSX.Element => {
        return <BasePreview name={item.payload.name} />
    },
}
