import { BackgroundRefresher } from './background-refresher'
import { PostgresRouter, PostgresUse } from './db/postgres'
import { logger } from './logger'

// Tree node types for boolean expression tree
export type FilterNode = FilterConditionNode | FilterAndNode | FilterOrNode | FilterNotNode

export interface FilterConditionNode {
    type: 'condition'
    field: 'event_name' | 'distinct_id'
    operator: 'exact' | 'contains'
    value: string
}

export interface FilterAndNode {
    type: 'and'
    children: FilterNode[]
}

export interface FilterOrNode {
    type: 'or'
    children: FilterNode[]
}

export interface FilterNotNode {
    type: 'not'
    child: FilterNode
}

export interface EventFilterRule {
    id: string
    team_id: number
    filter_tree: FilterNode
}

/**
 * Manages per-team event filter config loaded from Postgres.
 * One filter per team. Uses BackgroundRefresher to load all enabled filters.
 */
export class EventFilterManager {
    private refresher: BackgroundRefresher<Map<number, EventFilterRule>>

    constructor(private postgres: PostgresRouter) {
        this.refresher = new BackgroundRefresher(async () => this.fetchAllFilters(), 60_000)

        void this.refresher.get().catch((error) => {
            logger.error('Failed to initialize event filter config', { error })
        })
    }

    /** Returns the filter for a team, or null. Non-blocking. */
    getFilter(teamId: number): EventFilterRule | null {
        return this.refresher.tryGet()?.get(teamId) ?? null
    }

    private async fetchAllFilters(): Promise<Map<number, EventFilterRule>> {
        const { rows } = await this.postgres.query<{
            id: string
            team_id: number
            filter_tree: FilterNode
        }>(
            PostgresUse.COMMON_READ,
            `SELECT id, team_id, filter_tree
             FROM posthog_eventfilterconfig
             WHERE enabled = true`,
            [],
            'fetchAllEventFilters'
        )

        const map = new Map<number, EventFilterRule>()
        for (const row of rows) {
            map.set(row.team_id, {
                id: row.id,
                team_id: row.team_id,
                filter_tree: row.filter_tree,
            })
        }

        logger.debug('🔁 event_filter_manager - refreshed filters', { teamCount: map.size })
        return map
    }
}
