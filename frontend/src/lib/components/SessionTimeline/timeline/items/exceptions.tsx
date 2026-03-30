import { IconWarning } from '@posthog/icons'
import { Link } from '@posthog/lemon-ui'

import { ErrorTrackingException, ErrorTrackingRuntime } from 'lib/components/Errors/types'
import { getRuntimeFromLib } from 'lib/components/Errors/utils'
import { Dayjs, dayjs } from 'lib/dayjs'
import { urls } from 'scenes/urls'

import { RuntimeIcon } from 'products/error_tracking/frontend/components/RuntimeIcon'

import { ItemCategory, ItemLoader, ItemRenderer, TimelineItem } from '..'
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

/**
 * Static loader that holds a single pre-built exception item in memory.
 * Used when there is no session ID but we still want to show the current
 * exception on the timeline alongside exception steps.
 */
export class StaticExceptionLoader implements ItemLoader<ExceptionItem> {
    private readonly item: ExceptionItem

    constructor(uuid: string, timestamp: Dayjs, properties?: Record<string, any>) {
        const runtime: ErrorTrackingRuntime = getRuntimeFromLib(properties?.$lib)
        const exceptionList: ErrorTrackingException[] | undefined = properties?.$exception_list
        this.item = {
            id: uuid,
            category: ItemCategory.ERROR_TRACKING,
            timestamp: dayjs.utc(timestamp),
            payload: {
                runtime,
                type: exceptionList?.[0]?.type ?? 'Exception',
                message: exceptionList?.[0]?.value ?? '',
                fingerprint: properties?.$exception_fingerprint ?? '',
                issue_id: properties?.$exception_issue_id ?? '',
            },
        }
    }

    async loadBefore(cursor: Dayjs): Promise<ExceptionItem[]> {
        return this.item.timestamp.isBefore(cursor) ? [this.item] : []
    }

    async loadAfter(cursor: Dayjs): Promise<ExceptionItem[]> {
        return this.item.timestamp.isAfter(cursor) ? [this.item] : []
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
