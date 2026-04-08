import { useValues } from 'kea'
import { useMemo } from 'react'

import { LemonSelect } from '@posthog/lemon-ui'

import { PropertyFilters } from 'lib/components/PropertyFilters/PropertyFilters'
import { TaxonomicFilterGroupType } from 'lib/components/TaxonomicFilter/types'
import { LemonField } from 'lib/lemon-ui/LemonField'

import { AnyPropertyFilter, CyclotronJobFiltersType, HogFunctionConfigurationContextId } from '~/types'

import { hogFunctionConfigurationLogic } from '../configuration/hogFunctionConfigurationLogic'

type FilterOption = { value: string; label: string }

// NOTE: This is all a bit WIP and will be improved upon over time
// TODO: Make this more advanced with sub type filtering etc.
// TODO: Make it possible for the renderer to limit the options based on the type
/**
 * Options for the 'Trigger' field on the new destination page
 */
const INTERNAL_EVENT_OPTIONS: Record<string, FilterOption[]> = {
    'error-tracking': [
        { label: 'Error tracking issue created', value: '$error_tracking_issue_created' },
        { label: 'Error tracking issue reopened', value: '$error_tracking_issue_reopened' },
    ],
    'insight-alerts': [{ label: 'Insight alert firing', value: '$insight_alert_firing' }],
    'logs-alerting': [
        { label: 'Log alert firing', value: '$logs_alert_firing' },
        { label: 'Log alert resolved', value: '$logs_alert_resolved' },
    ],
    'discussion-mention': [{ label: 'Discussion mention', value: '$discussion_mention_created' }],
    'experiment-alerts': [{ label: 'Experiment metric significant', value: '$experiment_metric_significant' }],
    default: [
        { label: 'Team activity', value: '$activity_log_entry_created' },
        { label: 'Early access feature updated', value: '$early_access_feature_updated' },
    ],
}

export const getProductEventFilterOptions = (contextId: HogFunctionConfigurationContextId): FilterOption[] => {
    return INTERNAL_EVENT_OPTIONS[contextId] ?? INTERNAL_EVENT_OPTIONS['default']
}

/** Returns all internal events across all contexts, deduplicated by value. */
export const getAllInternalEventFilterOptions = (): FilterOption[] => {
    const seen = new Set<string>()
    const result: FilterOption[] = []
    for (const options of Object.values(INTERNAL_EVENT_OPTIONS)) {
        for (const option of options) {
            if (!seen.has(option.value)) {
                seen.add(option.value)
                result.push(option)
            }
        }
    }
    return result
}

const INTERNAL_EVENT_IDS = new Set(getAllInternalEventFilterOptions().map((o) => o.value))

/** Returns true if the given event ID is an internal event (e.g. $activity_log_entry_created). */
export const isInternalEvent = (eventId: string): boolean => INTERNAL_EVENT_IDS.has(eventId)

export const getProductEventPropertyFilterOptions = (contextId: HogFunctionConfigurationContextId): string[] => {
    switch (contextId) {
        case 'activity-log':
            return [
                'id',
                'unread',
                'organization_id',
                'was_impersonated',
                'is_system',
                'activity',
                'item_id',
                'scope',
                'detail',
                'detail.name',
                'detail.changes',
                'created_at',
            ]
        case 'error-tracking':
            return [
                '$exception_types',
                '$exception_values',
                '$exception_sources',
                '$exception_functions',
                '$exception_handled',
            ]
    }

    return []
}

const getSimpleFilterValue = (value?: CyclotronJobFiltersType): string | undefined => {
    return value?.events?.[0]?.id
}

const setSimpleFilterValue = (options: FilterOption[], value: string): CyclotronJobFiltersType => {
    return {
        events: [
            {
                name: options.find((option) => option.value === value)?.label,
                id: value,
                type: 'events',
            },
        ],
    }
}

export function HogFunctionFiltersInternal(): JSX.Element {
    const { contextId } = useValues(hogFunctionConfigurationLogic)

    const options = useMemo(() => getProductEventFilterOptions(contextId), [contextId])

    const taxonomicGroupTypes = useMemo(() => {
        if (contextId === 'error-tracking') {
            return [
                TaxonomicFilterGroupType.ErrorTrackingIssues,
                TaxonomicFilterGroupType.ErrorTrackingProperties,
                TaxonomicFilterGroupType.EventProperties,
            ]
        } else if (contextId === 'insight-alerts') {
            return [TaxonomicFilterGroupType.Events]
        } else if (contextId === 'activity-log') {
            return [TaxonomicFilterGroupType.ActivityLogProperties]
        }
        return []
    }, [contextId])

    return (
        <div className="p-3 rounded border deprecated-space-y-2 bg-surface-primary">
            <LemonField name="filters" label="Trigger">
                {({ value, onChange }) => (
                    <>
                        <div className="text-xs text-secondary">Choose what event should trigger this destination</div>
                        <LemonSelect
                            options={options}
                            value={getSimpleFilterValue(value)}
                            onChange={(value) => onChange(setSimpleFilterValue(options, value))}
                            placeholder="Select a filter"
                        />
                        {taxonomicGroupTypes.length > 0 ? (
                            <PropertyFilters
                                key={contextId}
                                propertyFilters={value?.properties ?? []}
                                taxonomicGroupTypes={taxonomicGroupTypes}
                                onChange={(properties: AnyPropertyFilter[]) => {
                                    onChange({
                                        ...value,
                                        properties,
                                    })
                                }}
                                pageKey={`hog-function-internal-property-filters-${contextId}`}
                                buttonSize="small"
                                disablePopover
                            />
                        ) : null}
                    </>
                )}
            </LemonField>
        </div>
    )
}
