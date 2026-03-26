import { useValues } from 'kea'

import { LemonTable, LemonTag } from '@posthog/lemon-ui'

import { humanFriendlyDetailedTime } from 'lib/utils'
import { SceneExport } from 'scenes/sceneTypes'

import { SceneContent } from '~/layout/scenes/components/SceneContent'
import { SceneTitleSection } from '~/layout/scenes/components/SceneTitleSection'
import { ProductKey } from '~/queries/schema/schema-general'

import { AnalyzedSite, featuresRepositoryLogic } from './featuresRepositoryLogic'

export const scene: SceneExport = {
    component: FeaturesRepositoryScene,
    logic: featuresRepositoryLogic,
    productKey: ProductKey.FEATURES_REPOSITORY,
}

export function FeaturesRepositoryScene(): JSX.Element {
    const { sites, sitesLoading } = useValues(featuresRepositoryLogic)

    return (
        <SceneContent>
            <SceneTitleSection
                name="Features repository"
                description="Analyzed websites and their product/feature taxonomy"
                resourceType={{ type: 'apps' }}
            />
            <LemonTable
                loading={sitesLoading}
                dataSource={sites}
                columns={[
                    {
                        title: 'Site',
                        width: '40%',
                        render: (_: unknown, site: AnalyzedSite) => (
                            <div className="flex items-center gap-3 py-2">
                                {site.screenshot ? (
                                    <img
                                        src={site.screenshot}
                                        alt={site.domain}
                                        className="w-12 h-12 rounded object-cover flex-shrink-0 border"
                                    />
                                ) : (
                                    <div className="w-12 h-12 rounded bg-bg-3000 flex-shrink-0 border flex items-center justify-center text-muted text-xs">
                                        N/A
                                    </div>
                                )}
                                <div className="min-w-0">
                                    <div className="font-semibold truncate">{site.domain}</div>
                                    <div className="text-xs text-muted truncate">{site.title}</div>
                                </div>
                            </div>
                        ),
                    },
                    {
                        title: 'Description',
                        width: '30%',
                        render: (_: unknown, site: AnalyzedSite) => (
                            <div className="text-xs text-muted line-clamp-3">{site.description}</div>
                        ),
                    },
                    {
                        title: 'Stats',
                        align: 'center',
                        render: (_: unknown, site: AnalyzedSite) => (
                            <div className="flex gap-2 items-center justify-center">
                                <LemonTag type="highlight">{site.products_count} products</LemonTag>
                                <LemonTag type="completion">{site.features_count} features</LemonTag>
                                <LemonTag>{site.pages_count} pages</LemonTag>
                            </div>
                        ),
                    },
                    {
                        title: 'Last updated',
                        align: 'right',
                        render: (_: unknown, site: AnalyzedSite) => (
                            <span className="text-xs text-muted whitespace-nowrap">
                                {site.last_updated ? humanFriendlyDetailedTime(site.last_updated) : '–'}
                            </span>
                        ),
                    },
                ]}
            />
        </SceneContent>
    )
}
