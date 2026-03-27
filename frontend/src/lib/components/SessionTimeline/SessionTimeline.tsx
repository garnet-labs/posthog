import { cva } from 'cva'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'

import { Link, Spinner } from '@posthog/lemon-ui'

import { Dayjs } from 'lib/dayjs'
import { useScrollObserver } from 'lib/hooks/useScrollObserver'
import { IconVerticalAlignCenter } from 'lib/lemon-ui/icons'
import { ButtonPrimitive, ButtonPrimitiveProps } from 'lib/ui/Button/ButtonPrimitives'
import { cn } from 'lib/utils/css-classes'

import { ItemCategory, ItemCollector, ItemRenderer, RendererProps, TimelineItem } from './timeline'

const ITEM_HEIGHT_PX = 32 // matches h-[2rem]
const BUFFER_FACTOR = 1.5

function calculateBatchSize(containerEl: HTMLElement | null): number {
    if (!containerEl) {
        return 25
    }
    return Math.max(10, Math.ceil((containerEl.clientHeight / ITEM_HEIGHT_PX) * BUFFER_FACTOR))
}

export interface SessionTimelineHandle {
    scrollToItem: (itemId: string) => void
}

export interface SessionTimelineProps {
    ref: React.RefObject<SessionTimelineHandle>
    collector: ItemCollector
    selectedItemId?: string
    className?: string
    onTimeClick?: (time: Dayjs) => void
}

export function SessionTimeline({
    ref,
    collector,
    selectedItemId,
    className,
    onTimeClick,
}: SessionTimelineProps): JSX.Element {
    const [items, setItems] = useState<TimelineItem[]>([])
    const [categories, setCategories] = useState<ItemCategory[]>(() => collector.getAllCategories())
    const [loading, setLoading] = useState(false)
    const [scrollLoading, setScrollLoading] = useState<'before' | 'after' | null>(null)
    const scrollLoadingRef = useRef<'before' | 'after' | null>(null)

    function toggleCategory(category: ItemCategory): void {
        setCategories((prevCategories) => {
            if (prevCategories.includes(category)) {
                return prevCategories.filter((c) => c !== category)
            }
            return [...prevCategories, category]
        })
    }

    const containerRef = useRef<HTMLDivElement | null>(null)

    const scrollToItem = useCallback((uuid: string) => {
        const item = containerRef.current?.querySelector(`[data-item-id="${uuid}"]`)
        if (item) {
            requestAnimationFrame(() => {
                item.scrollIntoView({ behavior: 'instant', block: 'center' })
            })
        }
    }, [])

    // Initial load + auto-fill
    useEffect(() => {
        collector.clear()
        setLoading(true)

        const batch = calculateBatchSize(containerRef.current)

        Promise.all([collector.loadBefore(categories, batch), collector.loadAfter(categories, batch)])
            .then(async () => {
                setItems(collector.collectItems())

                if (selectedItemId) {
                    // Wait for DOM update then scroll
                    await new Promise<void>((r) => requestAnimationFrame(r))
                    scrollToItem(selectedItemId)
                }

                // Auto-fill: keep loading until container overflows or data exhausted
                const el = containerRef.current
                if (el) {
                    await new Promise<void>((r) => requestAnimationFrame(r))

                    while (el.scrollHeight <= el.clientHeight) {
                        const canBefore = collector.hasBefore(categories)
                        const canAfter = collector.hasAfter(categories)
                        if (!canBefore && !canAfter) {
                            break
                        }

                        if (canBefore) {
                            const scrollTop = el.scrollTop
                            const scrollHeight = el.scrollHeight
                            await collector.loadBefore(categories, batch)
                            setItems(collector.collectItems())
                            await new Promise<void>((r) => requestAnimationFrame(r))
                            el.scrollTop = scrollTop + (el.scrollHeight - scrollHeight)
                        } else if (canAfter) {
                            await collector.loadAfter(categories, batch)
                            setItems(collector.collectItems())
                            await new Promise<void>((r) => requestAnimationFrame(r))
                        }
                    }
                }
            })
            .finally(() => setLoading(false))
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [collector, categories, selectedItemId])

    // Scroll-triggered loading (throttled via scroll observer)
    const handleScrollTop = useCallback(async () => {
        if (!collector.hasBefore(categories) || scrollLoadingRef.current) {
            return
        }
        scrollLoadingRef.current = 'before'
        setScrollLoading('before')
        try {
            const el = containerRef.current
            const scrollTop = el?.scrollTop || 0
            const scrollHeight = el?.scrollHeight || 0
            const batch = calculateBatchSize(el)
            await collector.loadBefore(categories, batch)
            setItems(collector.collectItems())
            requestAnimationFrame(() => {
                const newScrollHeight = el?.scrollHeight || 0
                if (el) {
                    el.scrollTop = scrollTop + (newScrollHeight - scrollHeight)
                }
            })
        } finally {
            scrollLoadingRef.current = null
            setScrollLoading(null)
        }
    }, [collector, categories])

    const handleScrollBottom = useCallback(async () => {
        if (!collector.hasAfter(categories) || scrollLoadingRef.current) {
            return
        }
        scrollLoadingRef.current = 'after'
        setScrollLoading('after')
        try {
            const batch = calculateBatchSize(containerRef.current)
            await collector.loadAfter(categories, batch)
            setItems(collector.collectItems())
        } finally {
            scrollLoadingRef.current = null
            setScrollLoading(null)
        }
    }, [collector, categories])

    const scrollRefCb = useScrollObserver({
        onScrollTop: handleScrollTop,
        onScrollBottom: handleScrollBottom,
    })

    useImperativeHandle(ref, () => ({ scrollToItem }))

    const isLoading = loading || scrollLoading !== null

    return (
        <div className={cn('flex h-full', className)}>
            <div className="flex flex-col justify-between items-center p-1 border-r border-gray-3 shrink-0">
                <CategoryToggleGroup>
                    {collector.getCategories().map((cat) => (
                        <ItemCategoryToggle
                            active={categories.includes(cat)}
                            key={cat}
                            category={cat}
                            onClick={() => toggleCategory(cat)}
                        >
                            {collector.getRenderer(cat)?.categoryIcon}
                        </ItemCategoryToggle>
                    ))}
                </CategoryToggleGroup>
                {items.find((item) => item.id === selectedItemId) && (
                    <ButtonPrimitive
                        tooltip="Scroll to item"
                        tooltipPlacement="right"
                        iconOnly
                        size="xs"
                        onClick={() => selectedItemId && scrollToItem(selectedItemId)}
                    >
                        <IconVerticalAlignCenter />
                    </ButtonPrimitive>
                )}
            </div>
            <div
                ref={(el) => {
                    scrollRefCb(el)
                    containerRef.current = el
                }}
                className="h-full w-full overflow-y-auto relative"
                style={{ scrollbarGutter: 'stable' }}
            >
                {(loading || scrollLoading === 'before') && (
                    <div className={cn(itemContainer({ selected: false }), 'justify-start')}>
                        <Spinner />
                        <span className="text-secondary">loading...</span>
                    </div>
                )}
                {items.map((item) => {
                    const renderer = collector.getRenderer(item.category)
                    if (!renderer) {
                        return null
                    }
                    return (
                        <SessionTimelineItemContainer
                            renderer={renderer}
                            key={item.id}
                            item={item}
                            selected={item.id === selectedItemId}
                            onTimeClick={onTimeClick}
                        />
                    )
                })}
                {!loading && scrollLoading === 'after' && (
                    <div className={cn(itemContainer({ selected: false }), 'justify-start')}>
                        <Spinner />
                        <span className="text-secondary">loading...</span>
                    </div>
                )}
                {!isLoading && items.length === 0 && (
                    <div className={cn(itemContainer({ selected: false }), 'justify-center')}>
                        <span className="text-secondary text-xs">No items</span>
                    </div>
                )}
            </div>
        </div>
    )
}

const itemContainer = cva({
    base: 'flex justify-between gap-2 items-center px-2 w-full h-[2rem]',
    variants: {
        selected: {
            true: 'bg-[var(--gray-1)] border-1 border-accent',
            false: 'border-b border-[var(--gray-2)]',
        },
    },
})

type SessionTimelineItemContainerProps = RendererProps<TimelineItem> & {
    renderer: ItemRenderer<TimelineItem>
    selected: boolean
    onTimeClick?: (timestamp: Dayjs) => void
}

const SessionTimelineItemContainer = forwardRef<HTMLDivElement, SessionTimelineItemContainerProps>(
    function SessionTimelineItemContainer(
        { renderer, item, selected, onTimeClick }: SessionTimelineItemContainerProps,
        ref
    ): JSX.Element {
        return (
            <div ref={ref} className={itemContainer({ selected })} data-item-id={item.id}>
                <span className="text-xs text-tertiary w-[20px] shrink-0 text-center">
                    <renderer.sourceIcon item={item} />
                </span>
                <span className="text-xs text-tertiary w-[50px] shrink-0 text-center">
                    <Link className="text-tertiary hover:text-accent" onClick={() => onTimeClick?.(item.timestamp)}>
                        {item.timestamp.format('HH:mm:ss')}
                    </Link>
                </span>
                <div className="shrink-0 w-[20px] text-center">{renderer.categoryIcon}</div>
                <div className="flex-grow">
                    <renderer.render item={item} />
                </div>
            </div>
        )
    }
)

function CategoryToggleGroup({ children }: { children: React.ReactNode }): JSX.Element {
    return (
        <div
            className={cn(
                'flex flex-col gap-0.5',
                '[&>button]:rounded [&>button]:border-0 [&>button]:px-2 [&>button]:py-1.5',
                '[&>button:hover]:bg-fill-button-tertiary-hover'
            )}
        >
            {children}
        </div>
    )
}

const itemCategoryToggle = cva({
    base: 'shrink-0 transition-colors',
    variants: {
        active: {
            true: 'text-accent',
            false: 'text-muted opacity-50',
        },
    },
})

export function ItemCategoryToggle({
    active,
    category,
    ...props
}: ButtonPrimitiveProps & { category: ItemCategory }): JSX.Element {
    return (
        <ButtonPrimitive
            iconOnly
            tooltip={active ? `Hide ${category}` : `Show ${category}`}
            tooltipPlacement="right"
            className={itemCategoryToggle({ active })}
            {...props}
        />
    )
}
