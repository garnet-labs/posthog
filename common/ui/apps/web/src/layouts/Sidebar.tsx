import * as React from 'react'
import { NavLink } from 'react-router'

import { cn } from '@posthog/ui-primitives'

import { getRegistryByCategory } from '../registry/registry'

export function Sidebar(): React.ReactElement {
    const categories = getRegistryByCategory()

    return (
        <aside className="sticky top-0 flex h-screen w-[240px] shrink-0 flex-col overflow-y-auto border-r border-border p-4">
            <NavLink to="/" className="mb-6 text-lg font-semibold">
                PostHog UI
            </NavLink>

            <nav className="flex flex-col gap-6">
                <div>
                    <NavLink
                        to="/"
                        end
                        className={({ isActive }) =>
                            cn(
                                'block rounded-md px-2 py-1 text-sm',
                                isActive
                                    ? 'bg-accent text-accent-foreground'
                                    : 'text-muted-foreground hover:text-foreground'
                            )
                        }
                    >
                        Overview
                    </NavLink>
                </div>

                {categories.map((category) => (
                    <div key={category.name}>
                        <h3 className="mb-1 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                            {category.name}
                        </h3>
                        <ul className="flex flex-col">
                            {category.components.map((comp) => (
                                <li key={comp.slug}>
                                    <NavLink
                                        to={`/components/${comp.slug}`}
                                        className={({ isActive }) =>
                                            cn(
                                                'block rounded-md px-2 py-1 text-sm',
                                                isActive
                                                    ? 'bg-accent font-medium text-accent-foreground'
                                                    : 'text-muted-foreground hover:text-foreground'
                                            )
                                        }
                                    >
                                        {comp.name}
                                    </NavLink>
                                </li>
                            ))}
                        </ul>
                    </div>
                ))}
            </nav>
        </aside>
    )
}
