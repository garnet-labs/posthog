import { FilterNode } from '../../utils/event-filter-manager'
import { ApplyEventFiltersInput, evaluateNode } from './apply-event-filters-step'

function makeInput(event: string, distinctId: string): ApplyEventFiltersInput {
    return {
        event: { event, distinct_id: distinctId, uuid: 'test-uuid' } as any,
        team: { id: 1 } as any,
        headers: { event, distinct_id: distinctId } as any,
    }
}

describe('evaluateNode', () => {
    describe('empty groups are conservative (never drop)', () => {
        it('empty AND returns false (does NOT drop)', () => {
            const node: FilterNode = { type: 'and', children: [] }
            expect(evaluateNode(node, makeInput('$pageview', 'user-1'))).toBe(false)
        })

        it('empty OR returns false (does NOT drop)', () => {
            const node: FilterNode = { type: 'or', children: [] }
            expect(evaluateNode(node, makeInput('$pageview', 'user-1'))).toBe(false)
        })

        it('NOT wrapping empty AND returns true (inverts false)', () => {
            const node: FilterNode = { type: 'not', child: { type: 'and', children: [] } }
            expect(evaluateNode(node, makeInput('$pageview', 'user-1'))).toBe(true)
        })

        it('NOT wrapping empty OR returns true (inverts false)', () => {
            const node: FilterNode = { type: 'not', child: { type: 'or', children: [] } }
            expect(evaluateNode(node, makeInput('$pageview', 'user-1'))).toBe(true)
        })

        it('AND with only empty child groups returns false', () => {
            const node: FilterNode = {
                type: 'and',
                children: [
                    { type: 'or', children: [] },
                    { type: 'or', children: [] },
                ],
            }
            expect(evaluateNode(node, makeInput('$pageview', 'user-1'))).toBe(false)
        })
    })

    describe('condition matching', () => {
        it('exact match on event_name', () => {
            const node: FilterNode = { type: 'condition', field: 'event_name', operator: 'exact', value: '$pageview' }
            expect(evaluateNode(node, makeInput('$pageview', 'user-1'))).toBe(true)
            expect(evaluateNode(node, makeInput('$click', 'user-1'))).toBe(false)
        })

        it('exact match on distinct_id', () => {
            const node: FilterNode = { type: 'condition', field: 'distinct_id', operator: 'exact', value: 'bot-1' }
            expect(evaluateNode(node, makeInput('$pageview', 'bot-1'))).toBe(true)
            expect(evaluateNode(node, makeInput('$pageview', 'user-1'))).toBe(false)
        })

        it('contains match on event_name', () => {
            const node: FilterNode = { type: 'condition', field: 'event_name', operator: 'contains', value: 'page' }
            expect(evaluateNode(node, makeInput('$pageview', 'user-1'))).toBe(true)
            expect(evaluateNode(node, makeInput('$click', 'user-1'))).toBe(false)
        })

        it('contains match on distinct_id', () => {
            const node: FilterNode = { type: 'condition', field: 'distinct_id', operator: 'contains', value: 'bot-' }
            expect(evaluateNode(node, makeInput('$pageview', 'bot-crawler'))).toBe(true)
            expect(evaluateNode(node, makeInput('$pageview', 'real-user'))).toBe(false)
        })

        it('returns false for missing field value', () => {
            const node: FilterNode = { type: 'condition', field: 'distinct_id', operator: 'exact', value: 'test' }
            const input: ApplyEventFiltersInput = {
                event: { event: '$pageview', uuid: 'test-uuid' } as any,
                team: { id: 1 } as any,
                headers: { event: '$pageview' } as any,
            }
            expect(evaluateNode(node, input)).toBe(false)
        })
    })

    describe('AND logic', () => {
        it('all conditions must match', () => {
            const node: FilterNode = {
                type: 'and',
                children: [
                    { type: 'condition', field: 'event_name', operator: 'exact', value: '$pageview' },
                    { type: 'condition', field: 'distinct_id', operator: 'contains', value: 'bot-' },
                ],
            }
            expect(evaluateNode(node, makeInput('$pageview', 'bot-crawler'))).toBe(true)
            expect(evaluateNode(node, makeInput('$pageview', 'real-user'))).toBe(false)
            expect(evaluateNode(node, makeInput('$click', 'bot-crawler'))).toBe(false)
        })
    })

    describe('OR logic', () => {
        it('any condition can match', () => {
            const node: FilterNode = {
                type: 'or',
                children: [
                    { type: 'condition', field: 'event_name', operator: 'exact', value: '$drop_me' },
                    { type: 'condition', field: 'event_name', operator: 'exact', value: '$also_drop' },
                ],
            }
            expect(evaluateNode(node, makeInput('$drop_me', 'user-1'))).toBe(true)
            expect(evaluateNode(node, makeInput('$also_drop', 'user-1'))).toBe(true)
            expect(evaluateNode(node, makeInput('$keep_me', 'user-1'))).toBe(false)
        })
    })

    describe('NOT logic', () => {
        it('inverts a condition', () => {
            const node: FilterNode = {
                type: 'not',
                child: { type: 'condition', field: 'event_name', operator: 'exact', value: '$keep_me' },
            }
            expect(evaluateNode(node, makeInput('$keep_me', 'user-1'))).toBe(false)
            expect(evaluateNode(node, makeInput('$other', 'user-1'))).toBe(true)
        })
    })

    describe('complex trees', () => {
        it('OR of AND groups (classic DNF)', () => {
            // DROP WHERE (event = "$drop_me") OR (event = "$internal" AND distinct_id ~ "bot-")
            const node: FilterNode = {
                type: 'or',
                children: [
                    { type: 'condition', field: 'event_name', operator: 'exact', value: '$drop_me' },
                    {
                        type: 'and',
                        children: [
                            { type: 'condition', field: 'event_name', operator: 'exact', value: '$internal' },
                            { type: 'condition', field: 'distinct_id', operator: 'contains', value: 'bot-' },
                        ],
                    },
                ],
            }
            expect(evaluateNode(node, makeInput('$drop_me', 'anyone'))).toBe(true)
            expect(evaluateNode(node, makeInput('$internal', 'bot-crawler'))).toBe(true)
            expect(evaluateNode(node, makeInput('$internal', 'real-user'))).toBe(false)
            expect(evaluateNode(node, makeInput('$pageview', 'bot-crawler'))).toBe(false)
        })

        it('NOT wrapping an OR (allowlist pattern)', () => {
            // DROP WHERE NOT (event = "allowed_1" OR event = "allowed_2")
            const node: FilterNode = {
                type: 'not',
                child: {
                    type: 'or',
                    children: [
                        { type: 'condition', field: 'event_name', operator: 'exact', value: 'allowed_1' },
                        { type: 'condition', field: 'event_name', operator: 'exact', value: 'allowed_2' },
                    ],
                },
            }
            expect(evaluateNode(node, makeInput('allowed_1', 'user-1'))).toBe(false)
            expect(evaluateNode(node, makeInput('allowed_2', 'user-1'))).toBe(false)
            expect(evaluateNode(node, makeInput('other_event', 'user-1'))).toBe(true)
        })
    })
})
