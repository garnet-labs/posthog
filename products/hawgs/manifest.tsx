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
        ProductTaxonomySite: {
            name: 'Product taxonomy site',
            import: () => import('./frontend/ProductTaxonomySiteScene'),
            projectBased: true,
        },
    },
    routes: {
        '/product_taxonomy': ['ProductTaxonomy', 'productTaxonomy'],
        '/product_taxonomy/:domain': ['ProductTaxonomySite', 'productTaxonomySite'],
    },
    urls: {
        productTaxonomy: (): string => '/product_taxonomy',
        productTaxonomySite: (domain: string): string => `/product_taxonomy/${domain}`,
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
