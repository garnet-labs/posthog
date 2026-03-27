import { useValues } from 'kea'
import { useState } from 'react'

import { IconEllipsis } from '@posthog/icons'
import { LemonBadge, LemonCheckbox, LemonDivider, LemonMenu } from '@posthog/lemon-ui'

import { TaxonomicFilterGroupType } from 'lib/components/TaxonomicFilter/types'
import { FEATURE_FLAGS } from 'lib/constants'
import { LemonButton } from 'lib/lemon-ui/LemonButton'
import { Tooltip } from 'lib/lemon-ui/Tooltip'
import { featureFlagLogic } from 'lib/logic/featureFlagLogic'
import { getEventNamesForAction } from 'lib/utils'

import { actionsModel } from '~/models/actionsModel'
import { ChartDisplayCategory, EntityTypes } from '~/types'

import { LocalFilter } from '../entityFilterLogic'
import { FunnelStepAggregationTargetSelect } from './FunnelStepAggregationTargetSelect'
import { MathSelector } from './MathSelector'
import { MathAvailability } from './types'

function FunnelStepMenuField({ label, children }: { label: string; children: JSX.Element }): JSX.Element {
    return (
        <div className="mb-2.5 mx-2">
            <h5 className="mx-0 my-1">{label}</h5>
            {children}
        </div>
    )
}

interface ActionFilterRowMenuProps {
    index: number
    isTrendsContext: boolean
    isFunnelContext: boolean
    isStepOptional: (step: number) => boolean
    math?: string
    mathGroupTypeIndex?: number | null
    mathAvailability: MathAvailability
    trendsDisplayCategory: ChartDisplayCategory | null
    readOnly: boolean
    query: Record<string, any>
    filter: LocalFilter
    hideRename: boolean
    hideDuplicate: boolean
    hideDeleteBtn: boolean
    singleFilter: boolean
    onMathSelect: (index: number, value: string | undefined) => void
    onUpdateOptional: (checked: boolean) => void
    onUpdateFunnelAggregationTarget: (
        funnelAggregationTarget: string | undefined,
        funnelAggregationTargetType: TaxonomicFilterGroupType | undefined
    ) => void
    renameRowButton: JSX.Element
    duplicateRowButton: JSX.Element
    deleteButton: JSX.Element
}

export function ActionFilterRowMenu({
    index,
    isTrendsContext,
    isFunnelContext,
    isStepOptional,
    math,
    mathGroupTypeIndex,
    mathAvailability,
    trendsDisplayCategory,
    readOnly,
    query,
    filter,
    hideRename,
    hideDuplicate,
    hideDeleteBtn,
    singleFilter,
    onMathSelect,
    onUpdateOptional,
    onUpdateFunnelAggregationTarget,
    renameRowButton,
    duplicateRowButton,
    deleteButton,
}: ActionFilterRowMenuProps): JSX.Element {
    const { featureFlags } = useValues(featureFlagLogic)
    const { actions } = useValues(actionsModel)

    const [isMenuVisible, setIsMenuVisible] = useState(false)

    const wrapWithClose = (element: JSX.Element): JSX.Element => (
        <div onClick={() => setIsMenuVisible(false)}>{element}</div>
    )

    const hasFunnelCustomStepAggregationFlag =
        featureFlags[FEATURE_FLAGS.PRODUCT_ANALYTICS_FUNNEL_CUSTOM_STEP_AGGREGATION]
    const funnelStepAggregationEventNames =
        filter.type === EntityTypes.EVENTS && filter.id
            ? [String(filter.id)]
            : filter.type === EntityTypes.ACTIONS && filter.id
              ? getEventNamesForAction(parseInt(String(filter.id)), actions)
              : []

    const menuItems: JSX.Element[] = []

    // MathSelector for funnels only (trends shows it inline)
    if (isFunnelContext) {
        menuItems.push(
            <FunnelStepMenuField label="Event matching">
                <MathSelector
                    math={math}
                    mathGroupTypeIndex={mathGroupTypeIndex}
                    index={index}
                    onMathSelect={onMathSelect}
                    disabled={readOnly}
                    style={{ maxWidth: '100%', width: 'initial' }}
                    mathAvailability={mathAvailability}
                    trendsDisplayCategory={trendsDisplayCategory}
                    query={query}
                />
            </FunnelStepMenuField>
        )
    }

    // Custom aggregation target for funnels only
    if (
        isFunnelContext &&
        hasFunnelCustomStepAggregationFlag &&
        (filter.type === EntityTypes.EVENTS || filter.type === EntityTypes.ACTIONS)
    ) {
        menuItems.push(
            <FunnelStepMenuField label="Aggregating by">
                <FunnelStepAggregationTargetSelect
                    filter={filter}
                    eventNames={funnelStepAggregationEventNames}
                    onChange={onUpdateFunnelAggregationTarget}
                />
            </FunnelStepMenuField>
        )
    }

    // Optional step checkbox for funnels only
    if (isFunnelContext && index > 0) {
        menuItems.push(
            <Tooltip title="Optional steps show conversion rates from the last mandatory step, but are not necessary to move to the next step in the funnel">
                <div className="px-2 py-1">
                    <LemonCheckbox
                        checked={!!filter.optionalInFunnel}
                        onChange={(checked) => onUpdateOptional(checked)}
                        label="Optional step"
                    />
                </div>
            </Tooltip>
        )
    }

    // Separator for funnels only
    if (isFunnelContext) {
        menuItems.push(<LemonDivider />)
    }

    if (!hideRename) {
        menuItems.push(wrapWithClose(renameRowButton))
    }

    if (!singleFilter) {
        if (!hideDuplicate) {
            menuItems.push(wrapWithClose(duplicateRowButton))
        }
        if (!hideDeleteBtn) {
            menuItems.push(wrapWithClose(deleteButton))
        }
    }

    return (
        <div className="relative">
            <LemonMenu
                placement={isTrendsContext ? 'bottom-end' : 'bottom-start'}
                visible={isMenuVisible}
                closeOnClickInside={false}
                onVisibilityChange={setIsMenuVisible}
                items={menuItems.map((el) => ({ label: () => el }))}
            >
                <LemonButton
                    size="medium"
                    aria-label="Show more actions"
                    data-attr={`more-button-${index}`}
                    icon={<IconEllipsis />}
                    noPadding
                />
            </LemonMenu>
            <LemonBadge
                position="top-right"
                size="small"
                visible={isFunnelContext && (math != null || isStepOptional(index + 1))}
            />
        </div>
    )
}
