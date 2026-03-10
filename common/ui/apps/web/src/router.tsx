import { createBrowserRouter } from 'react-router'

import { DocsLayout } from './layouts/DocsLayout'
import { ComponentPage } from './pages/ComponentPage'
import { HomePage } from './pages/HomePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { registry } from './registry/registry'

export const router = createBrowserRouter([
    {
        element: <DocsLayout />,
        children: [
            { index: true, element: <HomePage /> },
            ...registry.map((entry) => ({
                path: `components/${entry.slug}`,
                element: <ComponentPage slug={entry.slug} />,
            })),
            { path: '*', element: <NotFoundPage /> },
        ],
    },
])
