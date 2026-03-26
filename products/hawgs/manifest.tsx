import { urls } from 'scenes/urls'

import { FileSystemIconType, ProductKey } from '~/queries/schema/schema-general'
import { ProductManifest } from '~/types'

export const manifest: ProductManifest = {
    name: 'Product taxonomy',
    scenes: {
        ProductTaxonomy: {
            name: 'Product taxonomy',
            import: () => import('./frontend/ProductTaxonomyScene'),
            projectBased: true,
            description: 'Analyze websites to discover their product and feature taxonomy.',
            iconType: 'apps',
        },
    },
    routes: {
        '/product_taxonomy': ['ProductTaxonomy', 'productTaxonomy'],
    },
    urls: {
        productTaxonomy: (): string => '/product_taxonomy',
    },
    treeItemsProducts: [
        {
            path: 'Product taxonomy',
            intents: [ProductKey.PRODUCT_TAXONOMY],
            category: 'Features',
            type: 'product_taxonomy',
            href: urls.productTaxonomy(),
            iconType: 'apps' as FileSystemIconType,
            sceneKey: 'ProductTaxonomy',
        },
    ],
}
