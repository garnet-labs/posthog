import { IconTerminal } from '@posthog/icons'

import api from 'lib/api'
import { Dayjs, dayjs } from 'lib/dayjs'

import { hogql } from '~/queries/utils'

import { RuntimeIcon } from 'products/error_tracking/frontend/components/RuntimeIcon'

import { ItemCategory, ItemLoader, ItemRenderer, TimelineItem } from '..'
import { BasePreview } from './base'

export interface ConsoleLogItem extends TimelineItem {
    payload: {
        level: string
        message: string
    }
}

export const consoleLogRenderer: ItemRenderer<ConsoleLogItem> = {
    sourceIcon: () => <RuntimeIcon runtime="web" />,
    categoryIcon: <IconTerminal />,
    render: ({ item }): JSX.Element => {
        return (
            <BasePreview
                name={`Console ${item.payload.level}`}
                description={item.payload.message}
                descriptionTitle={item.payload.message}
            />
        )
    },
}

const WINDOW_HOURS = 1

export class ConsoleLogLoader implements ItemLoader<ConsoleLogItem> {
    constructor(
        private readonly sessionId: string,
        private readonly centerTimestamp: Dayjs
    ) {}

    async loadBefore(cursor: Dayjs, limit: number): Promise<ConsoleLogItem[]> {
        const windowStart = this.centerTimestamp.subtract(WINDOW_HOURS, 'hours')
        const query = hogql`SELECT timestamp, level, message FROM log_entries WHERE log_source = 'session_replay' AND log_source_id = ${this.sessionId} AND timestamp >= ${windowStart} AND timestamp < ${cursor} ORDER BY timestamp DESC LIMIT ${limit}`
        return this.execute(query)
    }

    async loadAfter(cursor: Dayjs, limit: number): Promise<ConsoleLogItem[]> {
        const windowEnd = this.centerTimestamp.add(WINDOW_HOURS, 'hours')
        const query = hogql`SELECT timestamp, level, message FROM log_entries WHERE log_source = 'session_replay' AND log_source_id = ${this.sessionId} AND timestamp > ${cursor} AND timestamp <= ${windowEnd} ORDER BY timestamp ASC LIMIT ${limit}`
        return this.execute(query)
    }

    private async execute(query: ReturnType<typeof hogql>): Promise<ConsoleLogItem[]> {
        const response = await api.queryHogQL(query, { scene: 'ReplaySingle', productKey: 'session_replay' })
        return response.results.map(
            (row) =>
                ({
                    id: `log-${String(row[0])}-${String(row[1])}-${String(row[2])}`,
                    category: ItemCategory.CONSOLE_LOGS,
                    timestamp: dayjs.utc(row[0]),
                    payload: {
                        level: row[1],
                        message: row[2],
                    },
                }) as ConsoleLogItem
        )
    }
}
