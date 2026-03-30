import { IconEye } from '@posthog/icons'
import { Link } from '@posthog/lemon-ui'

import { ErrorTrackingRuntime } from 'lib/components/Errors/types'

import { RuntimeIcon } from 'products/error_tracking/frontend/components/RuntimeIcon'

import { ItemRenderer, TimelineItem } from '..'
import { BasePreview } from './base'

export interface PageItem extends TimelineItem {
    payload: {
        runtime: ErrorTrackingRuntime
        url: string
    }
}

export const pageRenderer: ItemRenderer<PageItem> = {
    sourceIcon: ({ item }) => <RuntimeIcon runtime={item.payload.runtime} />,
    categoryIcon: <IconEye />,
    render: ({ item }): JSX.Element => {
        return (
            <BasePreview
                name="Pageview"
                description={
                    <Link className="text-secondary hover:text-accent" subtle to={item.payload.url} target="_blank">
                        {getUrlPathname(item.payload.url)}
                    </Link>
                }
                descriptionTitle={item.payload.url}
            />
        )
    },
}

function getUrlPathname(url: string): string {
    try {
        const parsedUrl = new URL(url)
        return parsedUrl.pathname
    } catch {
        return url
    }
}
