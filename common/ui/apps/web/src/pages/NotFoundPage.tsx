import * as React from 'react'
import { Link } from 'react-router'

import { Button } from '@posthog/ui-primitives'

export function NotFoundPage(): React.ReactElement {
    return (
        <div className="flex flex-col items-center justify-center py-24">
            <h1 className="text-4xl font-bold">404</h1>
            <p className="mt-2 text-muted-foreground">Page not found.</p>
            <Button asChild className="mt-4">
                <Link to="/">Go home</Link>
            </Button>
        </div>
    )
}
