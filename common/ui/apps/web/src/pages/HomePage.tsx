import * as React from 'react'
import { Link } from 'react-router'

import { registry } from '../registry/registry'

export function HomePage(): React.ReactElement {
    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-3xl font-bold">PostHog UI</h1>
                <p className="mt-2 text-lg text-muted-foreground">
                    A collection of accessible, composable React components built with Tailwind v4 and Base UI.
                </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
                {registry.map((entry) => (
                    <Link
                        key={entry.slug}
                        to={`/components/${entry.slug}`}
                        className="rounded-lg border border-border p-4 transition-colors hover:bg-accent"
                    >
                        <h3 className="font-medium">{entry.name}</h3>
                        <p className="mt-1 text-sm text-muted-foreground">{entry.description}</p>
                    </Link>
                ))}
            </div>
        </div>
    )
}
