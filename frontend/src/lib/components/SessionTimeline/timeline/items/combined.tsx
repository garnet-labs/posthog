/**
 * Combined event loader — fetches exceptions, pageviews, and custom events in a
 * single EventsQuery instead of 3 separate ones. Register the same instance for
 * all three event categories so the collector deduplicates it.
 */
import api from 'lib/api'
import { ErrorTrackingException, ErrorTrackingRuntime } from 'lib/components/Errors/types'
import { getRuntimeFromLib } from 'lib/components/Errors/utils'
import { Dayjs, dayjs } from 'lib/dayjs'

import { EventsQuery, NodeKind } from '~/queries/schema/schema-general'

import { ItemCategory, ItemLoader, TimelineItem } from '..'

const WINDOW_HOURS = 1

const SELECT = [
    'uuid',
    'event',
    'timestamp',
    'properties.$lib',
    'properties.$current_url',
    'properties.$exception_list',
    'properties.$exception_fingerprint',
    'properties.$exception_issue_id',
]

function buildWhere(sessionId: string): string[] {
    return [
        `equals($session_id, '${sessionId}')`,
        "or(equals(event, '$exception'), equals(event, '$pageview'), notEquals(left(event, 1), '$'))",
    ]
}

export class CombinedEventLoader implements ItemLoader<TimelineItem> {
    constructor(
        private readonly sessionId: string,
        private readonly centerTimestamp: Dayjs
    ) {}

    async loadBefore(cursor: Dayjs, limit: number): Promise<TimelineItem[]> {
        const query: EventsQuery = {
            kind: NodeKind.EventsQuery,
            select: SELECT,
            where: buildWhere(this.sessionId),
            after: cursor.subtract(WINDOW_HOURS, 'hours').toISOString(),
            before: cursor.toISOString(),
            orderBy: ['timestamp DESC'],
            limit,
        }
        const response = await api.query(query)
        return response.results.map(buildItem)
    }

    async loadAfter(cursor: Dayjs, limit: number): Promise<TimelineItem[]> {
        const query: EventsQuery = {
            kind: NodeKind.EventsQuery,
            select: SELECT,
            where: buildWhere(this.sessionId),
            after: cursor.toISOString(),
            before: this.centerTimestamp.add(WINDOW_HOURS, 'hours').toISOString(),
            orderBy: ['timestamp ASC'],
            limit,
        }
        const response = await api.query(query)
        return response.results.map(buildItem)
    }
}

function buildItem(evt: any[]): TimelineItem {
    const [uuid, event, timestamp, lib, currentUrl, rawExceptionList, exceptionFingerprint, exceptionIssueId] = evt
    const ts = dayjs.utc(timestamp)
    const runtime: ErrorTrackingRuntime = getRuntimeFromLib(lib)

    if (event === '$exception') {
        const exceptionList: ErrorTrackingException[] | undefined = parseIfString(rawExceptionList)
        return {
            id: uuid,
            category: ItemCategory.ERROR_TRACKING,
            timestamp: ts,
            payload: {
                runtime,
                type: exceptionList?.[0]?.type,
                message: exceptionList?.[0]?.value,
                fingerprint: exceptionFingerprint,
                issue_id: exceptionIssueId,
            },
        }
    }

    if (event === '$pageview') {
        return {
            id: uuid,
            category: ItemCategory.PAGE_VIEWS,
            timestamp: ts,
            payload: { runtime, url: currentUrl },
        }
    }

    // Custom event (anything not starting with $)
    return {
        id: uuid,
        category: ItemCategory.CUSTOM_EVENTS,
        timestamp: ts,
        payload: { runtime, name: event },
    }
}

function parseIfString<T>(value: unknown): T | undefined {
    if (value == null) {
        return undefined
    }
    if (typeof value === 'string') {
        try {
            return JSON.parse(value) as T
        } catch {
            return undefined
        }
    }
    return value as T
}
