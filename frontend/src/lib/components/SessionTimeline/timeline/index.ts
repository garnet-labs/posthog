import { Dayjs } from 'lib/dayjs'

export enum ItemCategory {
    ERROR_TRACKING = 'exceptions',
    EXCEPTION_STEPS = 'exception steps',
    CUSTOM_EVENTS = 'custom events',
    PAGE_VIEWS = 'pageviews',
    CONSOLE_LOGS = 'console logs',
}

export interface TimelineItem {
    id: string
    category: ItemCategory
    timestamp: Dayjs
    payload: any
    sortPriority?: number
}

export function compareTimelineItems(a: TimelineItem, b: TimelineItem): number {
    const timestampDiff = a.timestamp.diff(b.timestamp)
    if (timestampDiff !== 0) {
        return timestampDiff
    }

    const sortPriorityDiff = (a.sortPriority ?? 0) - (b.sortPriority ?? 0)
    if (sortPriorityDiff !== 0) {
        return sortPriorityDiff
    }

    const categoryDiff = a.category.localeCompare(b.category)
    if (categoryDiff !== 0) {
        return categoryDiff
    }

    return a.id.localeCompare(b.id)
}

export interface RendererProps<T extends TimelineItem> {
    item: T
}

export type ItemRenderer<T extends TimelineItem> = {
    sourceIcon: React.FC<RendererProps<T>>
    categoryIcon: React.ReactNode
    render: React.FC<RendererProps<T>>
}

/** Configurable time ranges (in hours) for adaptive query expansion. Tried in ascending order; stops at first non-empty result. */
export type TimeRangeConfig = number[]

export const DEFAULT_TIME_RANGES: TimeRangeConfig = [1, 6, 24]

export type ItemLoader<T extends TimelineItem> = {
    hasPrevious(index: Dayjs): boolean
    previousBatch(index: Dayjs, count: number): Promise<T[]>

    hasNext(index: Dayjs): boolean
    nextBatch(index: Dayjs, count: number): Promise<T[]>

    clear?(): void
}
// eslint-disable-next-line import/no-cycle
export * from './item-collector'
