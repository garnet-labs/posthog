import { Meta, StoryFn } from '@storybook/react'
import { useRef } from 'react'

import { Dayjs, dayjs } from 'lib/dayjs'
import { uuid } from 'lib/utils'

import { SessionTimeline, SessionTimelineHandle } from './SessionTimeline'
import { ItemCategory, ItemCollector, ItemLoader, ItemRenderer, TimelineItem } from './timeline'

const meta: Meta = {
    title: 'Components/SessionTimeline',
    parameters: {
        layout: 'centered',
        viewMode: 'story',
    },
}

export default meta

// ─── Mock items ──────────────────────────────────────────────────────────────

interface MockItem extends TimelineItem {
    payload: { label: string }
}

const ICON_BY_CATEGORY: Record<ItemCategory, string> = {
    [ItemCategory.ERROR_TRACKING]: '⚠️',
    [ItemCategory.EXCEPTION_STEPS]: '📋',
    [ItemCategory.CUSTOM_EVENTS]: '📊',
    [ItemCategory.PAGE_VIEWS]: '👁',
    [ItemCategory.CONSOLE_LOGS]: '🖥',
}

function mockRenderer(category: ItemCategory): ItemRenderer<MockItem> {
    return {
        sourceIcon: () => <span>{ICON_BY_CATEGORY[category]}</span>,
        categoryIcon: <span>{ICON_BY_CATEGORY[category]}</span>,
        render: ({ item }) => (
            <div className="flex justify-between items-center">
                <span className="font-medium text-xs">{item.payload.label}</span>
                <span className="text-secondary text-xs">{category}</span>
            </div>
        ),
    }
}

// ─── Mock loader ─────────────────────────────────────────────────────────────

function generateMockItems(
    category: ItemCategory,
    center: Dayjs,
    countBefore: number,
    countAfter: number,
    intervalMs: number = 2000
): MockItem[] {
    const items: MockItem[] = []
    for (let i = countBefore; i >= 1; i--) {
        items.push({
            id: uuid(),
            category,
            timestamp: center.subtract(i * intervalMs, 'millisecond'),
            payload: { label: `${category} -${i}` },
        })
    }
    for (let i = 1; i <= countAfter; i++) {
        items.push({
            id: uuid(),
            category,
            timestamp: center.add(i * intervalMs, 'millisecond'),
            payload: { label: `${category} +${i}` },
        })
    }
    return items
}

/**
 * In-memory mock loader with simple cursor-based pagination.
 */
class MockLoader implements ItemLoader<MockItem> {
    private items: MockItem[]
    private delayMs: number

    constructor(items: MockItem[], delayMs: number = 50) {
        this.items = items.sort((a, b) => a.timestamp.diff(b.timestamp))
        this.delayMs = delayMs
    }

    async loadBefore(cursor: Dayjs, limit: number): Promise<MockItem[]> {
        await this.delay()
        const before = this.items.filter((item) => item.timestamp.isBefore(cursor))
        return before.slice(-limit)
    }

    async loadAfter(cursor: Dayjs, limit: number): Promise<MockItem[]> {
        await this.delay()
        const after = this.items.filter((item) => item.timestamp.isAfter(cursor))
        return after.slice(0, limit)
    }

    private delay(): Promise<void> {
        return new Promise((resolve) => setTimeout(resolve, this.delayMs))
    }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function buildCollector(options: {
    center: Dayjs
    sessionId?: string
    categories?: { category: ItemCategory; countBefore: number; countAfter: number; intervalMs?: number }[]
    delayMs?: number
}): ItemCollector {
    const {
        center,
        sessionId = 'mock-session',
        categories = [
            { category: ItemCategory.ERROR_TRACKING, countBefore: 30, countAfter: 30 },
            { category: ItemCategory.PAGE_VIEWS, countBefore: 15, countAfter: 15 },
            { category: ItemCategory.CUSTOM_EVENTS, countBefore: 20, countAfter: 20 },
            { category: ItemCategory.CONSOLE_LOGS, countBefore: 50, countAfter: 50 },
        ],
        delayMs = 50,
    } = options

    const collector = new ItemCollector(sessionId, center)

    for (const { category, countBefore, countAfter, intervalMs } of categories) {
        const items = generateMockItems(category, center, countBefore, countAfter, intervalMs)
        collector.addCategory(category, mockRenderer(category), new MockLoader(items, delayMs))
    }

    return collector
}

// ─── Stories ─────────────────────────────────────────────────────────────────

const CENTER = dayjs.utc('2024-07-09T12:00:00.000Z')

/** Default timeline with multiple categories. Container is tall enough to trigger smart fill. */
export const Default: StoryFn = () => {
    const collector = buildCollector({ center: CENTER })
    const ref = useRef<SessionTimelineHandle>(null)
    return (
        <div style={{ width: 600, height: 500, border: '1px solid var(--border)' }}>
            <SessionTimeline ref={ref} collector={collector} />
        </div>
    )
}

/** Short container — smart fill loads just enough items to overflow. */
export const ShortContainer: StoryFn = () => {
    const collector = buildCollector({ center: CENTER })
    const ref = useRef<SessionTimelineHandle>(null)
    return (
        <div style={{ width: 600, height: 150, border: '1px solid var(--border)' }}>
            <SessionTimeline ref={ref} collector={collector} />
        </div>
    )
}

/** Tall container — smart fill loads more items to fill the space. */
export const TallContainer: StoryFn = () => {
    const collector = buildCollector({ center: CENTER })
    const ref = useRef<SessionTimelineHandle>(null)
    return (
        <div style={{ width: 600, height: 800, border: '1px solid var(--border)' }}>
            <SessionTimeline ref={ref} collector={collector} />
        </div>
    )
}

/** Only a few items total — should display without infinite-loading issues. */
export const FewItems: StoryFn = () => {
    const collector = buildCollector({
        center: CENTER,
        categories: [
            { category: ItemCategory.ERROR_TRACKING, countBefore: 2, countAfter: 1 },
            { category: ItemCategory.PAGE_VIEWS, countBefore: 1, countAfter: 1 },
        ],
    })
    const ref = useRef<SessionTimelineHandle>(null)
    return (
        <div style={{ width: 600, height: 400, border: '1px solid var(--border)' }}>
            <SessionTimeline ref={ref} collector={collector} />
        </div>
    )
}

/** Empty — no data in any loader. */
export const Empty: StoryFn = () => {
    const collector = buildCollector({
        center: CENTER,
        categories: [],
    })
    const ref = useRef<SessionTimelineHandle>(null)
    return (
        <div style={{ width: 600, height: 300, border: '1px solid var(--border)' }}>
            <SessionTimeline ref={ref} collector={collector} />
        </div>
    )
}

/** Slow loading — 500ms delay per batch to verify loading spinners. */
export const SlowLoading: StoryFn = () => {
    const collector = buildCollector({ center: CENTER, delayMs: 500 })
    const ref = useRef<SessionTimelineHandle>(null)
    return (
        <div style={{ width: 600, height: 400, border: '1px solid var(--border)' }}>
            <SessionTimeline ref={ref} collector={collector} />
        </div>
    )
}
SlowLoading.tags = ['test-skip']

/** Many items — 200 per category, for scroll performance testing. */
export const ManyItems: StoryFn = () => {
    const collector = buildCollector({
        center: CENTER,
        categories: [
            { category: ItemCategory.ERROR_TRACKING, countBefore: 200, countAfter: 200 },
            { category: ItemCategory.PAGE_VIEWS, countBefore: 200, countAfter: 200 },
            { category: ItemCategory.CUSTOM_EVENTS, countBefore: 200, countAfter: 200 },
            { category: ItemCategory.CONSOLE_LOGS, countBefore: 200, countAfter: 200 },
        ],
    })
    const ref = useRef<SessionTimelineHandle>(null)
    return (
        <div style={{ width: 600, height: 500, border: '1px solid var(--border)' }}>
            <SessionTimeline ref={ref} collector={collector} />
        </div>
    )
}

/** Single category — only console logs. */
export const SingleCategory: StoryFn = () => {
    const collector = buildCollector({
        center: CENTER,
        categories: [{ category: ItemCategory.CONSOLE_LOGS, countBefore: 50, countAfter: 50 }],
    })
    const ref = useRef<SessionTimelineHandle>(null)
    return (
        <div style={{ width: 600, height: 400, border: '1px solid var(--border)' }}>
            <SessionTimeline ref={ref} collector={collector} />
        </div>
    )
}
