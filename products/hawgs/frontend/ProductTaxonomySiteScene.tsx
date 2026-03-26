import { useValues } from 'kea'
import { useState } from 'react'

import { LemonModal, LemonTable, LemonTabs, LemonTag, Link } from '@posthog/lemon-ui'

import { humanFriendlyDetailedTime } from 'lib/utils'
import { SceneExport } from 'scenes/sceneTypes'

import { SceneContent } from '~/layout/scenes/components/SceneContent'
import { SceneTitleSection } from '~/layout/scenes/components/SceneTitleSection'

import {
    ProductTaxonomySiteLogicProps,
    SitePage,
    TaxonomyFeature,
    TaxonomyProduct,
    productTaxonomySiteLogic,
} from './productTaxonomySiteLogic'

export const scene: SceneExport = {
    component: ProductTaxonomySiteScene,
    logic: productTaxonomySiteLogic,
    paramsToProps: ({ params: { domain } }): ProductTaxonomySiteLogicProps => ({ domain }),
}

function ProductTaxonomySiteScene({ domain }: ProductTaxonomySiteLogicProps): JSX.Element {
    const { siteDetail, siteDetailLoading } = useValues(productTaxonomySiteLogic({ domain }))
    const [screenshotModal, setScreenshotModal] = useState<{ url: string; title: string } | null>(null)
    const [activeTab, setActiveTab] = useState<'pages' | 'taxonomy'>('pages')

    return (
        <SceneContent>
            <LemonModal isOpen={!!screenshotModal} onClose={() => setScreenshotModal(null)} simple title="">
                {screenshotModal && (
                    <img src={screenshotModal.url} alt={screenshotModal.title} className="w-full rounded" />
                )}
            </LemonModal>
            <SceneTitleSection
                name={domain}
                description="Pages analyzed for this website"
                resourceType={{ type: 'apps' }}
            />
            <LemonTabs
                activeKey={activeTab}
                onChange={(key) => setActiveTab(key as 'pages' | 'taxonomy')}
                tabs={[
                    {
                        key: 'pages',
                        label: `Pages${siteDetail ? ` (${siteDetail.pages.length})` : ''}`,
                        content: (
                            <LemonTable
                                loading={siteDetailLoading}
                                dataSource={siteDetail?.pages ?? []}
                                columns={[
                                    {
                                        title: 'Page',
                                        width: '35%',
                                        render: (_: unknown, page: SitePage) => (
                                            <div className="flex items-center gap-3 py-2">
                                                {page.screenshot ? (
                                                    <img
                                                        src={page.screenshot}
                                                        alt={page.title}
                                                        className="w-20 h-20 rounded object-cover flex-shrink-0 border cursor-pointer hover:opacity-80 transition-opacity"
                                                        onClick={() =>
                                                            setScreenshotModal({
                                                                url: page.screenshot!,
                                                                title: page.title,
                                                            })
                                                        }
                                                    />
                                                ) : (
                                                    <div className="w-20 h-20 rounded bg-bg-3000 flex-shrink-0 border flex items-center justify-center text-muted text-xs">
                                                        N/A
                                                    </div>
                                                )}
                                                <div className="min-w-0">
                                                    <div className="font-semibold text-sm truncate">{page.title}</div>
                                                    <div className="text-xs text-muted truncate">{page.url}</div>
                                                    {page.description && (
                                                        <div className="text-xs text-muted mt-1 line-clamp-2">
                                                            {page.description}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        ),
                                    },
                                    {
                                        title: 'Summary',
                                        width: '25%',
                                        render: (_: unknown, page: SitePage) => (
                                            <div className="text-xs text-muted line-clamp-4">{page.summary}</div>
                                        ),
                                    },
                                    {
                                        title: 'Related products',
                                        render: (_: unknown, page: SitePage) => (
                                            <div className="flex flex-wrap gap-1">
                                                {page.related_products.map((name) => (
                                                    <LemonTag key={name} type="highlight">
                                                        {name}
                                                    </LemonTag>
                                                ))}
                                            </div>
                                        ),
                                    },
                                    {
                                        title: 'Related features',
                                        render: (_: unknown, page: SitePage) => (
                                            <div className="flex flex-wrap gap-1">
                                                {page.related_features.map((name) => (
                                                    <LemonTag key={name} type="completion">
                                                        {name}
                                                    </LemonTag>
                                                ))}
                                            </div>
                                        ),
                                    },
                                    {
                                        title: 'Updated',
                                        align: 'right',
                                        render: (_: unknown, page: SitePage) => (
                                            <span className="text-xs text-muted whitespace-nowrap">
                                                {page.last_updated ? humanFriendlyDetailedTime(page.last_updated) : '–'}
                                            </span>
                                        ),
                                    },
                                ]}
                            />
                        ),
                    },
                    {
                        key: 'taxonomy',
                        label: `Taxonomy${siteDetail ? ` (${siteDetail.products.length} products)` : ''}`,
                        content: (
                            <LemonTable
                                loading={siteDetailLoading}
                                dataSource={siteDetail?.products ?? []}
                                columns={[
                                    {
                                        title: 'Product',
                                        width: '15%',
                                        render: (_: unknown, product: TaxonomyProduct) => (
                                            <div className="py-1">
                                                <div className="font-semibold text-sm">{product.name}</div>
                                                <div className="text-xs text-muted mt-0.5">
                                                    {product.features.length} features
                                                </div>
                                            </div>
                                        ),
                                    },
                                    {
                                        title: 'Description',
                                        width: '25%',
                                        render: (_: unknown, product: TaxonomyProduct) => (
                                            <div className="text-xs text-muted line-clamp-3">{product.description}</div>
                                        ),
                                    },
                                    {
                                        title: 'Code paths',
                                        width: '35%',
                                        render: (_: unknown, product: TaxonomyProduct) => (
                                            <div className="flex flex-col gap-0.5 overflow-hidden">
                                                {(product.code_paths ?? []).map((p) => (
                                                    <code key={p} className="font-mono text-[11px] text-muted truncate">
                                                        {p}
                                                    </code>
                                                ))}
                                            </div>
                                        ),
                                    },
                                    {
                                        title: 'Source URLs',
                                        width: '25%',
                                        render: (_: unknown, product: TaxonomyProduct) => (
                                            <div className="flex flex-col gap-0.5 overflow-hidden">
                                                {(product.source_urls ?? []).map((url) => (
                                                    <Link
                                                        key={url}
                                                        to={url}
                                                        target="_blank"
                                                        className="text-xs truncate"
                                                    >
                                                        {url.replace(/^https?:\/\//, '')}
                                                    </Link>
                                                ))}
                                            </div>
                                        ),
                                    },
                                ]}
                                expandable={{
                                    expandedRowRender: (product: TaxonomyProduct) => (
                                        <div className="py-2 px-4">
                                            {product.features.map((feature: TaxonomyFeature) => (
                                                <div
                                                    key={feature.name}
                                                    className="flex py-3 border-b last:border-b-0 border-border"
                                                >
                                                    <div className="w-[15%] flex-shrink-0 pl-2 border-l-2 border-primary">
                                                        <div className="font-medium text-sm">{feature.name}</div>
                                                    </div>
                                                    <div className="w-[25%] flex-shrink-0 text-xs text-muted px-2">
                                                        {feature.description}
                                                    </div>
                                                    <div className="w-[35%] flex-shrink-0 flex flex-col gap-0.5 overflow-hidden px-2">
                                                        {(feature.code_paths ?? []).map((p) => (
                                                            <code
                                                                key={p}
                                                                className="font-mono text-[11px] text-muted truncate"
                                                            >
                                                                {p}
                                                            </code>
                                                        ))}
                                                    </div>
                                                    <div className="w-[25%] flex-shrink-0 flex flex-col gap-0.5 overflow-hidden px-2">
                                                        {(feature.source_urls ?? []).map((url) => (
                                                            <Link
                                                                key={url}
                                                                to={url}
                                                                target="_blank"
                                                                className="text-xs truncate"
                                                            >
                                                                {url.replace(/^https?:\/\//, '')}
                                                            </Link>
                                                        ))}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ),
                                    rowExpandable: (product: TaxonomyProduct) => product.features.length > 0,
                                }}
                            />
                        ),
                    },
                ]}
            />
        </SceneContent>
    )
}
