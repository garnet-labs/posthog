import { Dayjs } from 'lib/dayjs'
import { TimeTree } from 'lib/utils/time-tree'

// eslint-disable-next-line import/no-cycle
import { compareTimelineItems, ItemCategory, ItemLoader, ItemRenderer, TimelineItem } from '.'

export class ItemCollector {
    sessionId: string
    timestamp: Dayjs
    beforeCursor: Dayjs
    afterCursor: Dayjs
    itemCache: TimeTree<TimelineItem>
    loaders: Map<ItemCategory, ItemLoader<TimelineItem>> = new Map()
    renderers: Map<ItemCategory, ItemRenderer<TimelineItem>> = new Map()

    constructor(sessionId: string, timestamp: Dayjs) {
        this.sessionId = sessionId
        this.timestamp = timestamp
        this.beforeCursor = this.timestamp
        this.afterCursor = this.timestamp
        this.itemCache = new TimeTree<TimelineItem>()
    }

    addCategory(category: ItemCategory, renderer: ItemRenderer<TimelineItem>, loader: ItemLoader<TimelineItem>): void {
        this.loaders.set(category, loader)
        this.renderers.set(category, renderer)
    }

    getAllCategories(): ItemCategory[] {
        return Array.from(this.loaders.keys())
    }

    clear(): void {
        this.beforeCursor = this.timestamp
        this.afterCursor = this.timestamp
        this.itemCache = new TimeTree<TimelineItem>()

        this.loaders.forEach((loader) => loader.clear?.())
    }

    getRenderer(category: ItemCategory): ItemRenderer<TimelineItem> | undefined {
        return this.renderers.get(category)
    }

    getLoader(category: ItemCategory): ItemLoader<TimelineItem> | undefined {
        return this.loaders.get(category)
    }

    getCategories(): ItemCategory[] {
        return Array.from(this.loaders.keys())
    }

    collectItems(): TimelineItem[] {
        return this.itemCache.getAll()
    }

    hasBefore(categories: ItemCategory[]): boolean {
        return categories
            .map((cat) => this.getLoader(cat))
            .some((loader) => !!loader && loader.hasPrevious(this.beforeCursor))
    }

    hasAfter(categories: ItemCategory[]): boolean {
        return categories
            .map((cat) => this.getLoader(cat))
            .some((loader) => !!loader && loader.hasNext(this.afterCursor))
    }

    async loadBefore(categories: ItemCategory[], count: number): Promise<void> {
        const loaders = categories
            .map((cat) => this.getLoader(cat))
            .filter((loader): loader is ItemLoader<TimelineItem> => !!loader)

        const batches = await Promise.all(loaders.map((loader) => loader.previousBatch(this.beforeCursor, count)))

        // Merge all items, sort descending (newest first), take closest `count`
        const allItems = batches.flat().sort((a, b) => compareTimelineItems(b, a))
        const selected = allItems.slice(0, count)

        if (selected.length > 0) {
            this.beforeCursor = selected[selected.length - 1].timestamp
        }

        this.itemCache.add(selected)
    }

    async loadAfter(categories: ItemCategory[], count: number): Promise<void> {
        const loaders = categories
            .map((cat) => this.getLoader(cat))
            .filter((loader): loader is ItemLoader<TimelineItem> => !!loader)

        const batches = await Promise.all(loaders.map((loader) => loader.nextBatch(this.afterCursor, count)))

        // Merge all items, sort ascending (oldest first), take closest `count`
        const allItems = batches.flat().sort(compareTimelineItems)
        const selected = allItems.slice(0, count)

        if (selected.length > 0) {
            this.afterCursor = selected[selected.length - 1].timestamp
        }

        this.itemCache.add(selected)
    }
}
