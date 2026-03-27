import { EventHeaders, PipelineEvent, Team, TimestampFormat } from '../../../types'
import { castTimestampOrNow } from '../../../utils/utils'
import { APP_METRICS_OUTPUT, AppMetricsOutput } from '../../analytics/outputs'
import { IngestionOutputs } from '../../outputs/ingestion-outputs'
import { PipelineResult, drop, ok } from '../../pipelines/results'
import { ProcessingStep } from '../../pipelines/steps'
import { EventFilterManager, evaluateFilterTree } from '../event-filters'

export interface ApplyEventFiltersInput {
    event: PipelineEvent
    team: Team
    headers: EventHeaders
}

/**
 * Creates a pipeline step that drops events matching customer-configured filters.
 *
 * Filters use a boolean expression tree with AND, OR, NOT, and condition nodes.
 * If the tree evaluates to true for an event, the event is dropped.
 * Dropped events are recorded as app metrics entries.
 */
export function createApplyEventFiltersStep<T extends ApplyEventFiltersInput>(
    manager: EventFilterManager,
    outputs: IngestionOutputs<AppMetricsOutput>
): ProcessingStep<T, T> {
    return function applyEventFiltersStep(input: T): Promise<PipelineResult<T>> {
        const filter = manager.getFilter(input.team.id)

        if (!filter) {
            return Promise.resolve(ok(input))
        }

        const dropped = evaluateFilterTree(filter.filter_tree, {
            event_name: input.event.event,
            distinct_id: input.event.distinct_id ?? input.headers.distinct_id ?? undefined,
        })

        if (dropped) {
            const metricMessage = {
                value: Buffer.from(
                    JSON.stringify({
                        team_id: input.team.id,
                        timestamp: castTimestampOrNow(null, TimestampFormat.ClickHouse),
                        app_source: 'event_filter',
                        app_source_id: filter.id,
                        metric_kind: 'other',
                        metric_name: 'dropped',
                        count: 1,
                    })
                ),
                key: Buffer.from(`${input.team.id}`),
            }

            const sideEffect = outputs.produce(APP_METRICS_OUTPUT, metricMessage)
            return Promise.resolve(drop('event_filter', [sideEffect]))
        }

        return Promise.resolve(ok(input))
    }
}
