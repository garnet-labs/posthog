import { EventHeaders, PipelineEvent, Team } from '../../types'
import { EventFilterManager, FilterConditionNode, FilterNode } from '../../utils/event-filter-manager'
import { PipelineWarning } from '../pipelines/pipeline.interface'
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
 */
export function createApplyEventFiltersStep<T extends ApplyEventFiltersInput>(
    manager: EventFilterManager
): ProcessingStep<T, T> {
    return function applyEventFiltersStep(input: T): Promise<PipelineResult<T>> {
        const filter = manager.getFilter(input.team.id)

        if (!filter) {
            return Promise.resolve(ok(input))
        }

        if (evaluateNode(filter.filter_tree, input)) {
            const warning: PipelineWarning = {
                type: 'event_dropped_by_filter',
                details: {
                    eventUuid: input.event.uuid,
                    event: input.event.event,
                    distinctId: input.event.distinct_id,
                    filterId: filter.id,
                },
                alwaysSend: false,
            }
            return Promise.resolve(drop('event_filter', [], [warning]))
        }

        return Promise.resolve(ok(input))
    }
}

/** Recursively evaluate a filter tree node against event input */
export function evaluateNode(node: FilterNode, input: ApplyEventFiltersInput): boolean {
    switch (node.type) {
        case 'condition':
            return evaluateCondition(node, input)
        case 'and':
            return node.children.every((child) => evaluateNode(child, input))
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
