import { appendFileSync, mkdirSync } from 'fs'
import path from 'path'

import { PostHogApiClient } from './posthog-api'
import type { HogbotNotificationEvent, HogbotScope } from './types'

function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => {
        setTimeout(resolve, ms)
    })
}

interface QueueBucket {
    events: HogbotNotificationEvent[]
    timer: NodeJS.Timeout | null
    flushing: Promise<void> | null
}

export class HogbotLogWriter {
    private readonly buckets = new Map<string, QueueBucket>()

    constructor(
        private readonly apiClient: PostHogApiClient,
        private readonly onFatal: (error: Error) => void,
        private readonly localLogPath?: string
    ) {}

    append(scope: HogbotScope, event: HogbotNotificationEvent, signalId?: string): void {
        this.appendLocal(event)
        const key = scope === 'research' ? `research:${signalId ?? ''}` : 'admin'
        const bucket = this.buckets.get(key) ?? { events: [], timer: null, flushing: null }
        bucket.events.push(event)
        this.buckets.set(key, bucket)

        if (bucket.timer) {
            clearTimeout(bucket.timer)
        }

        const isTerminal =
            event.notification.method === '_hogbot/result' ||
            (event.notification.method === '_hogbot/status' &&
                ['completed', 'failed', 'cancelled'].includes(String(event.notification.params.status ?? '')))

        if (isTerminal) {
            void this.flush(key, scope, signalId)
            return
        }

        bucket.timer = setTimeout(() => {
            void this.flush(key, scope, signalId)
        }, 500)
    }

    async flushAll(): Promise<void> {
        for (const [key] of this.buckets) {
            const scope = key.startsWith('research:') ? 'research' : 'admin'
            const signalId = key.startsWith('research:') ? key.slice('research:'.length) : undefined
            await this.flush(key, scope, signalId)
        }
    }

    private async flush(key: string, scope: HogbotScope, signalId?: string): Promise<void> {
        const bucket = this.buckets.get(key)
        if (!bucket || bucket.events.length === 0) {
            return
        }
        if (bucket.timer) {
            clearTimeout(bucket.timer)
            bucket.timer = null
        }
        if (bucket.flushing) {
            await bucket.flushing
            return
        }

        const events = bucket.events.splice(0, bucket.events.length)
        bucket.flushing = this.flushWithRetry(scope, events, signalId)
            .catch((error) => {
                this.onFatal(error instanceof Error ? error : new Error(String(error)))
            })
            .finally(() => {
                bucket.flushing = null
            })
        await bucket.flushing
    }

    private async flushWithRetry(
        scope: HogbotScope,
        events: HogbotNotificationEvent[],
        signalId?: string
    ): Promise<void> {
        let attempt = 0
        while (attempt < 10) {
            try {
                if (scope === 'research') {
                    if (!signalId) {
                        throw new Error('signalId is required for research log flushes')
                    }
                    await this.apiClient.appendResearchLog(signalId, events)
                } else {
                    await this.apiClient.appendAdminLog(events)
                }
                return
            } catch (error) {
                attempt += 1
                if (attempt >= 10) {
                    throw error instanceof Error ? error : new Error(String(error))
                }
                const delayMs = Math.min(1000 * 2 ** (attempt - 1), 30000)
                await sleep(delayMs)
            }
        }
    }

    private appendLocal(event: HogbotNotificationEvent): void {
        if (!this.localLogPath) {
            return
        }

        try {
            mkdirSync(path.dirname(this.localLogPath), { recursive: true })
            appendFileSync(this.localLogPath, `${JSON.stringify(event)}\n`, 'utf-8')
        } catch (error) {
            this.onFatal(error instanceof Error ? error : new Error(String(error)))
        }
    }
}
