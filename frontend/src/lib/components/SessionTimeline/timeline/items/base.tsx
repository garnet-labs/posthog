import api from 'lib/api'
import { Dayjs, dayjs } from 'lib/dayjs'
import { TimeTree } from 'lib/utils/time-tree'

import { EventsQuery, NodeKind } from '~/queries/schema/schema-general'
import { HogQLQueryString, hogql } from '~/queries/utils'

import { DEFAULT_TIME_RANGES, ItemLoader, TimelineItem, TimeRangeConfig } from '..'

export function BasePreview({
    name,
    description,
    descriptionTitle,
}: {
    name: React.ReactNode
    descriptionTitle?: string
    description?: React.ReactNode
}): JSX.Element {
    return (
        <div className="flex justify-between items-center">
            <span className="font-medium">{name}</span>
            {description && (
                <span className="text-secondary text-xs line-clamp-1 max-w-2/3 text-right" title={descriptionTitle}>
                    {description}
                </span>
            )}
        </div>
    )
}

/** Maximum number of fetch iterations per batch to prevent runaway loops. */
const MAX_FETCH_ITERATIONS = 5

export abstract class QueryLoader<T extends TimelineItem> implements ItemLoader<T> {
    private cache: TimeTree<T>
    private afterCursor: Dayjs
    private previousCursor: Dayjs
    private _hasNext: boolean = true
    private _hasPrevious: boolean = true
    protected readonly timeRanges: TimeRangeConfig

    constructor(
        private readonly initialTimestamp: Dayjs,
        timeRanges?: TimeRangeConfig
    ) {
        this.afterCursor = initialTimestamp
        this.previousCursor = initialTimestamp
        this.cache = new TimeTree<T>()
        this.timeRanges = timeRanges ?? DEFAULT_TIME_RANGES
    }

    clear(): void {
        this.afterCursor = this.initialTimestamp
        this.previousCursor = this.initialTimestamp
        this._hasNext = true
        this._hasPrevious = true
        this.cache.clear()
    }

    hasPrevious(to: Dayjs): boolean {
        if (this.cache.previous(to)) {
            return true
        }
        return this._hasPrevious
    }

    hasNext(from: Dayjs): boolean {
        if (this.cache.next(from)) {
            return true
        }
        return this._hasNext
    }

    async previousBatch(to: Dayjs, count: number): Promise<T[]> {
        let items = this.getCachedBefore(to, count)

        let iterations = 0
        while (items.length < count && this._hasPrevious && iterations < MAX_FETCH_ITERATIONS) {
            iterations++
            let loaded = false
            for (const hours of this.timeRanges) {
                const apiItems = await this.queryTo(this.previousCursor, count, hours)
                if (apiItems.length > 0) {
                    this.cache.add(apiItems)
                    this.previousCursor = apiItems[apiItems.length - 1].timestamp
                    loaded = true
                    break
                }
            }
            if (!loaded) {
                this._hasPrevious = false
                break
            }
            const newItems = this.getCachedBefore(to, count)
            if (newItems.length === items.length) {
                // No new items entered the cache — data is exhausted for this direction
                this._hasPrevious = false
                break
            }
            items = newItems
        }

        return items
    }

    async nextBatch(from: Dayjs, count: number): Promise<T[]> {
        let items = this.getCachedAfter(from, count)

        let iterations = 0
        while (items.length < count && this._hasNext && iterations < MAX_FETCH_ITERATIONS) {
            iterations++
            let loaded = false
            for (const hours of this.timeRanges) {
                const apiItems = await this.queryFrom(this.afterCursor, count, hours)
                if (apiItems.length > 0) {
                    this.cache.add(apiItems)
                    this.afterCursor = apiItems[apiItems.length - 1].timestamp
                    loaded = true
                    break
                }
            }
            if (!loaded) {
                this._hasNext = false
                break
            }
            const newItems = this.getCachedAfter(from, count)
            if (newItems.length === items.length) {
                // No new items entered the cache — data is exhausted for this direction
                this._hasNext = false
                break
            }
            items = newItems
        }

        return items
    }

    private getCachedBefore(to: Dayjs, count: number): T[] {
        const all = this.cache.getAll() // sorted ascending
        const before = all.filter((item) => item.timestamp.isBefore(to))
        return before.slice(-count)
    }

    private getCachedAfter(from: Dayjs, count: number): T[] {
        const all = this.cache.getAll() // sorted ascending
        const after = all.filter((item) => item.timestamp.isAfter(from))
        return after.slice(0, count)
    }

    abstract queryFrom(from: Dayjs, limit: number, timeRangeHours: number): Promise<T[]>
    abstract queryTo(to: Dayjs, limit: number, timeRangeHours: number): Promise<T[]>
    abstract buildItem(data: any): T
}

export abstract class EventLoader<T extends TimelineItem> extends QueryLoader<T> implements ItemLoader<T> {
    constructor(
        private sessionId: string,
        timestamp: Dayjs,
        timeRanges?: TimeRangeConfig
    ) {
        super(timestamp, timeRanges)
    }

    async queryFrom(from: Dayjs, limit: number, timeRangeHours: number): Promise<T[]> {
        const query = this.buildQueryFrom(from, limit, timeRangeHours)
        const response = await api.query(query)
        return response.results.map(this.buildItem)
    }

    async queryTo(to: Dayjs, limit: number, timeRangeHours: number): Promise<T[]> {
        const query = this.buildQueryTo(to, limit, timeRangeHours)
        const response = await api.query(query)
        return response.results.map(this.buildItem)
    }

    private buildQuery(limit: number): Partial<EventsQuery> {
        return {
            kind: NodeKind.EventsQuery,
            select: this.select(),
            where: [`equals($session_id, '${this.sessionId}')`, ...this.where()],
            limit: limit,
        }
    }

    buildQueryFrom(from: Dayjs, limit: number, timeRangeHours: number): EventsQuery {
        return {
            ...this.buildQuery(limit),
            after: from.toISOString(),
            before: from.add(timeRangeHours, 'hours').toISOString(),
            orderBy: ['timestamp ASC'],
        } as EventsQuery
    }

    buildQueryTo(to: Dayjs, limit: number, timeRangeHours: number): EventsQuery {
        return {
            ...this.buildQuery(limit),
            after: to.subtract(timeRangeHours, 'hours').toISOString(),
            before: to.toISOString(),
            orderBy: ['timestamp DESC'],
        } as EventsQuery
    }

    abstract select(): string[]
    abstract where(): string[]
    abstract buildItem(data: any): T
}

export abstract class LogEntryLoader<T extends TimelineItem> extends QueryLoader<T> implements ItemLoader<T> {
    async queryFrom(from: Dayjs, limit: number, timeRangeHours: number): Promise<T[]> {
        const query = this.buildQueryFrom(from, limit, timeRangeHours)
        const response = await api.queryHogQL(query, { scene: 'ReplaySingle', productKey: 'session_replay' })
        return response.results.map((row) =>
            this.buildItem({
                timestamp: dayjs.utc(row[0]),
                level: row[1],
                message: row[2],
            })
        )
    }

    async queryTo(to: Dayjs, limit: number, timeRangeHours: number): Promise<T[]> {
        const query = this.buildQueryTo(to, limit, timeRangeHours)
        const response = await api.queryHogQL(query, { scene: 'ReplaySingle', productKey: 'session_replay' })
        return response.results.map((row) =>
            this.buildItem({
                timestamp: dayjs.utc(row[0]),
                level: row[1],
                message: row[2],
            })
        )
    }

    buildQueryFrom(from: Dayjs, limit: number, timeRangeHours: number): HogQLQueryString {
        return hogql`SELECT timestamp, level, message FROM log_entries WHERE log_source = ${this.logSource()} AND log_source_id = ${this.logSourceId()} AND timestamp >= ${from} and timestamp <= ${from.add(timeRangeHours, 'hours')} ORDER BY timestamp ASC LIMIT ${limit}`
    }

    buildQueryTo(to: Dayjs, limit: number, timeRangeHours: number): HogQLQueryString {
        return hogql`SELECT timestamp, level, message FROM log_entries WHERE log_source = ${this.logSource()} AND log_source_id = ${this.logSourceId()} AND timestamp <= ${to} and timestamp >= ${to.subtract(timeRangeHours, 'hours')} ORDER BY timestamp DESC LIMIT ${limit}`
    }

    abstract logSource(): string
    abstract logSourceId(): string
    abstract buildItem(item: { timestamp: Dayjs; level: 'info' | 'warn' | 'error'; message: string }): T
}
