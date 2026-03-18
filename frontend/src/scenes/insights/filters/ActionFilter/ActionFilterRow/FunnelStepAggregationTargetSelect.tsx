import { useValues } from 'kea'

import { PropertyKeyInfo } from 'lib/components/PropertyKeyInfo'
import { TaxonomicFilterGroupType } from 'lib/components/TaxonomicFilter/types'
import { TaxonomicPopover } from 'lib/components/TaxonomicPopover/TaxonomicPopover'

import { groupsModel } from '~/models/groupsModel'
import { ActionFilter } from '~/types'

type FunnelStepAggregationTargetSelectProps = {
    eventNames: string[]
    filter: ActionFilter
    onChange: (
        funnelAggregationTarget: string | undefined,
        funnelAggregationTargetType: TaxonomicFilterGroupType | undefined
    ) => void
}

export function FunnelStepAggregationTargetSelect({
    eventNames,
    filter,
    onChange,
}: FunnelStepAggregationTargetSelectProps): JSX.Element {
    const { groupsTaxonomicTypes } = useValues(groupsModel)

    const aggregationTargetType = filter.funnelAggregationTargetType || TaxonomicFilterGroupType.EventProperties

    return (
        <TaxonomicPopover
            fullWidth
            groupType={aggregationTargetType}
            groupTypes={[
                TaxonomicFilterGroupType.EventProperties,
                TaxonomicFilterGroupType.PersonProperties,
                TaxonomicFilterGroupType.EventFeatureFlags,
                TaxonomicFilterGroupType.EventMetadata,
                ...groupsTaxonomicTypes,
                TaxonomicFilterGroupType.SessionProperties,
                TaxonomicFilterGroupType.HogQLExpression,
            ]}
            value={filter.funnelAggregationTarget || undefined}
            onChange={(funnelAggregationTarget, funnelAggregationTargetType) => {
                onChange(
                    funnelAggregationTarget ? String(funnelAggregationTarget) : undefined,
                    funnelAggregationTarget ? funnelAggregationTargetType : undefined
                )
            }}
            eventNames={eventNames}
            placeholder="Aggregating by ..."
            allowClear
            renderValue={(value) =>
                aggregationTargetType === TaxonomicFilterGroupType.HogQLExpression ? (
                    <code>{value}</code>
                ) : (
                    <PropertyKeyInfo value={value} type={aggregationTargetType} disablePopover />
                )
            }
        />
    )
}
