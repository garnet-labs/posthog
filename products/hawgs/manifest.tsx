import { urls } from 'scenes/urls'

import { FileSystemIconType, ProductKey } from '~/queries/schema/schema-general'
import { ProductManifest } from '~/types'

export const manifest: ProductManifest = {
    name: 'Features repository',
    scenes: {
        FeaturesRepository: {
            name: 'Features repository',
            import: () => import('./frontend/FeaturesRepositoryScene'),
            projectBased: true,
            description: 'Analyze websites to discover their product and feature taxonomy.',
            iconType: 'apps',
        },
    },
    routes: {
        '/features_repository': ['FeaturesRepository', 'featuresRepository'],
    },
    urls: {
        featuresRepository: (): string => '/features_repository',
    },
    treeItemsProducts: [
        {
            path: 'Features repository',
            intents: [ProductKey.FEATURES_REPOSITORY],
            category: 'Features',
            type: 'features_repository',
            href: urls.featuresRepository(),
            iconType: 'apps' as FileSystemIconType,
            sceneKey: 'FeaturesRepository',
        },
    ],
}
