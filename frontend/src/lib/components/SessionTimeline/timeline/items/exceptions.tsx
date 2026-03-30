import { IconWarning } from '@posthog/icons'
import { Link } from '@posthog/lemon-ui'

import { ErrorTrackingRuntime } from 'lib/components/Errors/types'
import { urls } from 'scenes/urls'

import { RuntimeIcon } from 'products/error_tracking/frontend/components/RuntimeIcon'

import { ItemRenderer, TimelineItem } from '..'
import { BasePreview } from './base'

export interface ExceptionItem extends TimelineItem {
    payload: {
        runtime: ErrorTrackingRuntime
        type: string
        message: string
        issue_id: string
        fingerprint: string
    }
}

export const exceptionRenderer: ItemRenderer<ExceptionItem> = {
    sourceIcon: ({ item }) => <RuntimeIcon runtime={item.payload.runtime} />,
    categoryIcon: <IconWarning />,
    render: ({ item }): JSX.Element => {
        const name = item.payload.type
        const description = item.payload.message
        const eventIssueId = item.payload.issue_id
        return (
            <BasePreview
                name={name}
                description={
                    <Link
                        className="text-secondary hover:text-accent"
                        subtle
                        to={urls.errorTrackingIssue(eventIssueId, {
                            fingerprint: item.payload.fingerprint,
                            timestamp: item.timestamp.toISOString(),
                        })}
                    >
                        {description}
                    </Link>
                }
                descriptionTitle={description}
            />
        )
    },
}
