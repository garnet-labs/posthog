import { EventHeaders, PipelineEvent, Team, TimestampFormat } from '../../types'
import { EventFilterManager, FilterConditionNode, FilterNode } from '../../utils/event-filter-manager'
import { castTimestampOrNow } from '../../utils/utils'
import { APP_METRICS_OUTPUT, AppMetricsOutput } from '../analytics/outputs'
import { IngestionOutputs } from '../outputs/ingestion-outputs'
import { PipelineResult, drop, ok } from '../pipelines/results'
import { ProcessingStep } from '../pipelines/steps'

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

        if (evaluateNode(filter.filter_tree, input)) {
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

/**
 * Recursively evaluate a filter tree node against event input.
 *
 * SAFETY: Empty groups are conservative (never drop):
 * - Empty AND returns false (not vacuous true) to avoid dropping all events
 * - Empty OR returns false (no children match)
 * This is intentional — when in doubt, don't drop. Dropping is irreversible,
 * while not dropping just means unwanted events get through temporarily.
 */
export function evaluateNode(node: FilterNode, input: ApplyEventFiltersInput): boolean {
    switch (node.type) {
        case 'condition':
            return evaluateCondition(node, input)
        case 'and':
            // Guard: [].every() is true in JS (vacuous truth) which would drop everything
            return node.children.length > 0 && node.children.every((child) => evaluateNode(child, input))
        case 'or':
            return node.children.some((child) => evaluateNode(child, input))
        case 'not':
            return !evaluateNode(node.child, input)
    }
}

function evaluateCondition(node: FilterConditionNode, input: ApplyEventFiltersInput): boolean {
    const value = getFieldValue(node.field, input)
    if (value === undefined || value === null) {
        return false
    }
    switch (node.operator) {
        case 'exact':
            return value === node.value
        case 'contains':
            return value.includes(node.value)
    }
}

function getFieldValue(field: FilterConditionNode['field'], input: ApplyEventFiltersInput): string | undefined | null {
    switch (field) {
        case 'event_name':
            return input.event.event
        case 'distinct_id':
            return input.event.distinct_id ?? input.headers.distinct_id
    }
}
