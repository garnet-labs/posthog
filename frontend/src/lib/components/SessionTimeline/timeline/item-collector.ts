import { Dayjs } from 'lib/dayjs'
import { TimeTree } from 'lib/utils/time-tree'

// eslint-disable-next-line import/no-cycle
import { compareTimelineItems, ItemCategory, ItemLoader, ItemRenderer, TimelineItem } from '.'

export class ItemCollector {
    readonly sessionId: string
    readonly timestamp: Dayjs

    private beforeCursor: Dayjs
    private afterCursor: Dayjs
    private _hasMoreBefore = true
    private _hasMoreAfter = true
    private itemCache: TimeTree<TimelineItem>

    private loaders = new Set<ItemLoader<TimelineItem>>()
    private renderers = new Map<ItemCategory, ItemRenderer<TimelineItem>>()

    constructor(sessionId: string, timestamp: Dayjs) {
        this.sessionId = sessionId
        this.timestamp = timestamp
        this.beforeCursor = timestamp
        this.afterCursor = timestamp
        this.itemCache = new TimeTree<TimelineItem>()
    }

    /**
     * Register a category with its renderer and loader.
     * The same loader instance may be shared across categories — it will only be
     * called once per load (Set deduplicates by identity).
     */
    addCategory(category: ItemCategory, renderer: ItemRenderer<TimelineItem>, loader: ItemLoader<TimelineItem>): void {
        this.renderers.set(category, renderer)
        this.loaders.add(loader)
    }

    getAllCategories(): ItemCategory[] {
        return Array.from(this.renderers.keys())
    }

    getRenderer(category: ItemCategory): ItemRenderer<TimelineItem> | undefined {
        return this.renderers.get(category)
    }

    collectItems(): TimelineItem[] {
        return this.itemCache.getAll()
    }

    get hasMoreBefore(): boolean {
        return this._hasMoreBefore
    }

    get hasMoreAfter(): boolean {
        return this._hasMoreAfter
    }

    clear(): void {
        this.beforeCursor = this.timestamp
        this.afterCursor = this.timestamp
        this._hasMoreBefore = true
        this._hasMoreAfter = true
        this.itemCache = new TimeTree<TimelineItem>()
    }

    async loadBefore(count: number): Promise<void> {
        if (!this._hasMoreBefore) {
            return
        }

        const loaders = Array.from(this.loaders)
        const perLoader = Math.max(1, Math.ceil(count / loaders.length))

        const batches = await Promise.all(loaders.map((loader) => loader.loadBefore(this.beforeCursor, perLoader)))

        const allItems = batches.flat().sort((a, b) => compareTimelineItems(b, a))
        const selected = allItems.slice(0, count)

        if (selected.length > 0) {
            this.beforeCursor = selected[selected.length - 1].timestamp
        } else {
            this._hasMoreBefore = false
        }

        this.itemCache.add(selected)
    }

    async loadAfter(count: number): Promise<void> {
        if (!this._hasMoreAfter) {
            return
        }

        const loaders = Array.from(this.loaders)
        const perLoader = Math.max(1, Math.ceil(count / loaders.length))

        const batches = await Promise.all(loaders.map((loader) => loader.loadAfter(this.afterCursor, perLoader)))

        const allItems = batches.flat().sort(compareTimelineItems)
        const selected = allItems.slice(0, count)

        if (selected.length > 0) {
            this.afterCursor = selected[selected.length - 1].timestamp
        } else {
            this._hasMoreAfter = false
        }

        this.itemCache.add(selected)
    }
}
