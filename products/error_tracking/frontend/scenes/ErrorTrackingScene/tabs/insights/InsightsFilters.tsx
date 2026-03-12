import { TaxonomicFilterGroupType } from 'lib/components/TaxonomicFilter/types'

import { QuickFilterContext } from '~/queries/schema/schema-general'
import { PropertyFilterType } from '~/types'

import { ErrorFilters } from 'products/error_tracking/frontend/components/IssueFilters'

import { ERROR_TRACKING_SCENE_LOGIC_KEY } from '../../errorTrackingSceneLogic'

const QUICK_FILTER_CONTEXT = QuickFilterContext.ErrorTrackingIssueFilters

const INSIGHTS_TAXONOMIC_GROUP_TYPES = [
    TaxonomicFilterGroupType.ErrorTrackingProperties,
    TaxonomicFilterGroupType.EventProperties,
    TaxonomicFilterGroupType.PersonProperties,
    TaxonomicFilterGroupType.Cohorts,
    TaxonomicFilterGroupType.HogQLExpression,
]

export function InsightsFilters({ reload }: { reload?: React.ReactNode }): JSX.Element {
    return (
        <ErrorFilters.Root>
            <div className="flex items-stretch rounded-full border border-[var(--color-border-primary)] bg-[var(--color-bg-fill-input)] [&_.LemonInput]:border-0 [&_.LemonInput]:rounded-none [&_.LemonInput]:shadow-none [&_.LemonInput]:bg-transparent [&_.LemonButton]:rounded-none [&_.LemonButton:not(:hover)]:bg-transparent">
                <div className="flex items-stretch rounded-l-full overflow-hidden">{reload}</div>
                <div className="w-px bg-[var(--color-border-primary)] shrink-0" />
                <div className="flex items-stretch overflow-hidden">
                    <ErrorFilters.DateRange type="tertiary" />
                </div>
                <div className="w-px bg-[var(--color-border-primary)] shrink-0" />
                <div className="flex items-stretch overflow-hidden">
                    <ErrorFilters.SettingsMenu
                        quickFilterContext={QUICK_FILTER_CONTEXT}
                        logicKey={ERROR_TRACKING_SCENE_LOGIC_KEY}
                        showIssueFilters={false}
                    />
                </div>
                <div className="w-px bg-[var(--color-border-primary)] shrink-0" />
                <div className="flex-1 rounded-r-full overflow-hidden">
                    <ErrorFilters.FilterGroup
                        taxonomicGroupTypes={INSIGHTS_TAXONOMIC_GROUP_TYPES}
                        excludeFilterTypes={[PropertyFilterType.ErrorTrackingIssue]}
                        quickFilterContext={QUICK_FILTER_CONTEXT}
                        logicKey={ERROR_TRACKING_SCENE_LOGIC_KEY}
                        showIssueFilters={false}
                    />
                </div>
            </div>
        </ErrorFilters.Root>
    )
}
