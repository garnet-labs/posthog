import * as React from 'react'
import { Outlet } from 'react-router'

import { Sidebar } from './Sidebar'
import { TableOfContents } from './TableOfContents'

export function DocsLayout(): React.ReactElement {
    return (
        <div className="flex min-h-screen">
            <Sidebar />
            <main id="main-content" className="flex-1 overflow-y-auto px-8 py-6">
                <div className="mx-auto max-w-3xl">
                    <Outlet />
                </div>
            </main>
            <TableOfContents />
        </div>
    )
}
