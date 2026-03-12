import { useActions, useValues } from 'kea'

import { IconFilter } from '@posthog/icons'
import { LemonButton, LemonMenu } from '@posthog/lemon-ui'

import { QuickFilterContext } from '~/queries/schema/schema-general'

import { ErrorFilters } from 'products/error_tracking/frontend/components/IssueFilters'
import {
    ORDER_BY_OPTIONS,
    issueQueryOptionsLogic,
} from 'products/error_tracking/frontend/components/IssueQueryOptions/issueQueryOptionsLogic'

import { ERROR_TRACKING_SCENE_LOGIC_KEY } from '../../errorTrackingSceneLogic'

const QUICK_FILTER_CONTEXT = QuickFilterContext.ErrorTrackingIssueFilters

export function IssuesFilters({
    reload,
    actions,
}: {
    reload?: React.ReactNode
    actions?: React.ReactNode
}): JSX.Element {
    const { orderBy, orderDirection } = useValues(issueQueryOptionsLogic)
    const { setOrderBy, setOrderDirection } = useActions(issueQueryOptionsLogic)

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
                    />
                </div>
                <div className="w-px bg-[var(--color-border-primary)] shrink-0" />
                <div className="flex-1 overflow-hidden">
                    <ErrorFilters.FilterGroup
                        quickFilterContext={QUICK_FILTER_CONTEXT}
                        logicKey={ERROR_TRACKING_SCENE_LOGIC_KEY}
                    />
                </div>
                <div className="w-px bg-[var(--color-border-primary)] shrink-0" />
                <div className="flex items-stretch overflow-hidden">
                    <LemonMenu
                        items={Object.entries(ORDER_BY_OPTIONS).map(([value, label]) => ({
                            label,
                            active: orderBy === value,
                            onClick: () => setOrderBy(value as typeof orderBy),
                        }))}
                    >
                        <LemonButton type="tertiary" size="small" icon={<IconFilter />}>
                            {ORDER_BY_OPTIONS[orderBy]}
                        </LemonButton>
                    </LemonMenu>
                </div>
                <div className="w-px bg-[var(--color-border-primary)] shrink-0" />
                <div className="flex items-stretch rounded-r-full overflow-hidden">
                    <LemonButton
                        type="tertiary"
                        size="small"
                        onClick={() => setOrderDirection(orderDirection === 'ASC' ? 'DESC' : 'ASC')}
                    >
                        <span className="text-xs px-1">{orderDirection}</span>
                    </LemonButton>
                </div>
            </div>
            {actions && (
                <div className="flex items-center">
                    <div className="ml-auto">{actions}</div>
                </div>
            )}
        </ErrorFilters.Root>
    )
}
