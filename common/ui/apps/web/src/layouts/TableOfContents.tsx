import * as React from 'react'
import { useLocation } from 'react-router'

import { cn } from '@posthog/ui-primitives'

interface TocItem {
    id: string
    text: string
    level: number
}

export function TableOfContents(): React.ReactElement {
    const [items, setItems] = React.useState<TocItem[]>([])
    const [activeId, setActiveId] = React.useState<string>('')
    const location = useLocation()

    React.useEffect(() => {
        const headings = document.querySelectorAll<HTMLElement>('#main-content h2[id], #main-content h3[id]')
        const tocItems: TocItem[] = Array.from(headings).map((el) => ({
            id: el.id,
            text: el.textContent ?? '',
            level: el.tagName === 'H2' ? 2 : 3,
        }))
        setItems(tocItems)
    }, [location.pathname])

    React.useEffect(() => {
        const observer = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting) {
                        setActiveId(entry.target.id)
                    }
                }
            },
            { rootMargin: '-80px 0px -80% 0px' }
        )

        const headings = document.querySelectorAll('#main-content h2[id], #main-content h3[id]')
        headings.forEach((el) => observer.observe(el))
        return (): void => observer.disconnect()
    }, [items])

    if (items.length === 0) {
        return <div className="w-[200px] shrink-0" />
    }

    return (
        <aside className="sticky top-0 hidden h-screen w-[200px] shrink-0 overflow-y-auto border-l border-border p-4 lg:block">
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">On this page</h4>
            <nav className="flex flex-col gap-0.5">
                {items.map((item) => (
                    // eslint-disable-next-line react/forbid-elements
                    <a
                        key={item.id}
                        href={`#${item.id}`}
                        className={cn(
                            'block py-1 text-sm',
                            item.level === 3 ? 'pl-3' : '',
                            activeId === item.id
                                ? 'font-medium text-foreground'
                                : 'text-muted-foreground hover:text-foreground'
                        )}
                    >
                        {item.text}
                    </a>
                ))}
            </nav>
        </aside>
    )
}
