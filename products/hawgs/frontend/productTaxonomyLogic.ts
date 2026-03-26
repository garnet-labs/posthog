import { afterMount, kea, path } from 'kea'
import { loaders } from 'kea-loaders'

import api from 'lib/api'

import type { productTaxonomyLogicType } from './productTaxonomyLogicType'

export interface AnalyzedSite {
    domain: string
    title: string
    description: string
    screenshot: string | null
    last_updated: string | null
    products_count: number
    features_count: number
    pages_count: number
}

export const productTaxonomyLogic = kea<productTaxonomyLogicType>([
    path(['scenes', 'product-taxonomy', 'productTaxonomyLogic']),
    loaders(() => ({
        sites: [
            [] as AnalyzedSite[],
            {
                loadSites: async () => {
                    const response = await api.get('api/environments/@current/product_taxonomy/')
                    return response.results
                },
            },
        ],
    })),
    afterMount(({ actions }) => {
        actions.loadSites()
    }),
])
