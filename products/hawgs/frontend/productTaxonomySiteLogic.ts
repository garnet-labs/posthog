import { afterMount, kea, key, path, props, selectors } from 'kea'
import { loaders } from 'kea-loaders'

import api from 'lib/api'
import { urls } from 'scenes/urls'

import { Breadcrumb } from '~/types'

import type { productTaxonomySiteLogicType } from './productTaxonomySiteLogicType'

export interface SitePage {
    url: string
    title: string
    description: string
    summary: string
    screenshot: string | null
    last_updated: string | null
    related_products: string[]
    related_features: string[]
}

export interface TaxonomyFeature {
    name: string
    description: string
    source_urls: string[]
    code_paths: string[]
}

export interface TaxonomyProduct {
    name: string
    description: string
    source_urls: string[]
    code_paths: string[]
    features: TaxonomyFeature[]
}

export interface SiteDetail {
    domain: string
    pages: SitePage[]
    products: TaxonomyProduct[]
}

export interface ProductTaxonomySiteLogicProps {
    domain: string
}

export const productTaxonomySiteLogic = kea<productTaxonomySiteLogicType>([
    path((key) => ['scenes', 'product-taxonomy', 'productTaxonomySiteLogic', key]),
    props({} as ProductTaxonomySiteLogicProps),
    key((props) => props.domain),
    loaders(({ props }) => ({
        siteDetail: [
            null as SiteDetail | null,
            {
                loadSiteDetail: async () => {
                    return await api.get(`api/environments/@current/product_taxonomy/${props.domain}/`)
                },
            },
        ],
    })),
    selectors({
        breadcrumbs: [
            (s) => [s.siteDetail],
            (siteDetail): Breadcrumb[] => [
                {
                    key: 'ProductTaxonomy',
                    name: 'Product taxonomy',
                    path: urls.productTaxonomy(),
                },
                {
                    key: 'ProductTaxonomySite',
                    name: siteDetail?.domain ?? 'Loading...',
                },
            ],
        ],
    }),
    afterMount(({ actions }) => {
        actions.loadSiteDetail()
    }),
])
