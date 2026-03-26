import { useValues } from 'kea'
import { useState } from 'react'

import { LemonModal, LemonTable, LemonTabs, LemonTag } from '@posthog/lemon-ui'

import { humanFriendlyDetailedTime } from 'lib/utils'
import { SceneExport } from 'scenes/sceneTypes'

import { SceneContent } from '~/layout/scenes/components/SceneContent'
import { SceneTitleSection } from '~/layout/scenes/components/SceneTitleSection'

import { ProductTaxonomySiteLogicProps, SitePage, productTaxonomySiteLogic } from './productTaxonomySiteLogic'

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
                        label: 'Taxonomy',
                        content: <div className="text-muted p-8 text-center">Taxonomy view coming soon</div>,
                    },
                ]}
            />
        </SceneContent>
    )
}
