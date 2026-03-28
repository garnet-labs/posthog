import {
    ExperimentEventExposureConfig,
    ExperimentMetric,
    FunnelsQuery,
    NodeKind,
    TrendsQuery,
    isExperimentFunnelMetric,
} from '~/queries/schema/schema-general'
import {
    BreakdownAttributionType,
    Experiment,
    FunnelConversionWindowTimeUnit,
    FunnelStepReference,
    FunnelVizType,
    StepOrderValue,
} from '~/types'

import {
    addExposureToMetric,
    compose,
    getExperimentDateRange,
    getExposureConfigEventsNode,
    getQuery,
} from '../../metricQueryUtils'

/**
 * Builds a FunnelsQuery from an experiment and its metric, suitable for use
 * as the `source` in a FunnelsActorsQuery (persons modal).
 *
 * Follows the same pattern as resultsBreakdownLogic to ensure the breakdown
 * attribution, exposure event, and filter options are consistent.
 */
export function buildExperimentFunnelsQuery(experiment: Experiment, metric: ExperimentMetric): FunnelsQuery | null {
    if (!isExperimentFunnelMetric(metric)) {
        return null
    }

    const exposureEventNode = getExposureConfigEventsNode(
        experiment.exposure_criteria?.exposure_config as ExperimentEventExposureConfig,
        {
            featureFlagKey: experiment.feature_flag_key,
            featureFlagVariants: experiment.parameters?.feature_flag_variants ?? [],
        }
    )

    // When using the default $feature_flag_called exposure, the variant value
    // lives in $feature_flag_response. For custom exposure events it's in
    // $feature/<flag_key>.
    const breakdownFilter = {
        breakdown:
            exposureEventNode.event === '$feature_flag_called'
                ? '$feature_flag_response'
                : `$feature/${experiment.feature_flag_key}`,
        breakdown_type: 'event' as const,
    }

    const queryBuilder = compose<ExperimentMetric, ExperimentMetric, FunnelsQuery | TrendsQuery | undefined>(
        addExposureToMetric(exposureEventNode),
        getQuery({
            filterTestAccounts: !!experiment.exposure_criteria?.filterTestAccounts,
            dateRange: getExperimentDateRange(experiment),
            breakdownFilter,
            funnelsFilter: {
                // Attribute the breakdown to the exposure step (step 0)
                breakdownAttributionType: BreakdownAttributionType.Step,
                breakdownAttributionValue: 0,
                funnelOrderType:
                    (isExperimentFunnelMetric(metric) && metric.funnel_order_type) || StepOrderValue.ORDERED,
                funnelStepReference: FunnelStepReference.total,
                funnelVizType: FunnelVizType.Steps,
                funnelWindowInterval: 14,
                funnelWindowIntervalUnit: FunnelConversionWindowTimeUnit.Day,
            },
        })
    )

    const query = queryBuilder(metric)
    if (!query || query.kind !== NodeKind.FunnelsQuery) {
        return null
    }

    return query
}
