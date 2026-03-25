/**
 * Product manifest for hogbot.
 *
 * Defines scenes, routes, URLs, and navigation for this product.
 */
import { urls } from 'scenes/urls'

import { ProductManifest } from '../../frontend/src/types'

export const manifest: ProductManifest = {
    name: 'Hogbot',
    scenes: {
        HogbotScene: {
            import: () => import('./frontend/HogbotScene'),
            projectBased: true,
            name: 'Hogbot',
            layout: 'app-container',
            description: 'AI agent sandbox with research and chat capabilities.',
        },
    },
    routes: {
        '/hogbot': ['HogbotScene', 'hogbotChat'],
        '/hogbot/research': ['HogbotScene', 'hogbotResearch'],
        '/hogbot/tasks': ['HogbotScene', 'hogbotTasks'],
    },
    redirects: {},
    urls: {
        hogbotChat: (): string => '/hogbot',
        hogbotResearch: (): string => '/hogbot/research',
        hogbotTasks: (): string => '/hogbot/tasks',
    },
    fileSystemTypes: {},
    treeItemsNew: [],
    treeItemsProducts: [
        {
            path: 'Hogbot',
            intents: [], // TODO: Add ProductKey.HOGBOT once it exists in schema-general
            category: 'Unreleased',
            href: urls.hogbotChat(),
            sceneKey: 'HogbotScene',
        },
    ],
}
