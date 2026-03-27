import { playerConfig } from '@posthog/rrweb'

export type LogType = 'log' | 'warning'
export type LoggingTimers = Record<LogType, NodeJS.Timeout | null>
export type BuiltLogging = {
    logger: playerConfig['logger']
    timers: LoggingTimers
}

export const makeNoOpLogger = (): BuiltLogging => {
    return {
        logger: {
            log: () => {},
            warn: () => {},
        },
        timers: { log: null, warning: null },
    }
}

const IGNORED_WARNING_PREFIXES = ['Could not find node with id']

export function isIgnoredWarning(category: string): boolean {
    return IGNORED_WARNING_PREFIXES.some((prefix) => category.startsWith(prefix))
}

export function categorizeWarning(args: any[]): string {
    const firstArg = args[0]
    if (typeof firstArg === 'string') {
        const trimmed = firstArg.slice(0, 80).trim()
        const firstSentence = trimmed.split(/[.!?\n]/)[0]
        return firstSentence || trimmed
    }
    if (firstArg instanceof Error) {
        return firstArg.message.slice(0, 80)
    }
    return 'unknown warning'
}

export const makeLogger = (
    onIncrement: (count: number) => void,
    onWarningSummary?: (summary: Record<string, number>) => void
): BuiltLogging => {
    const counters = {
        log: 0,
        warning: 0,
    }

    ;(window as any)[`__posthog_player_logs`] = (window as any)[`__posthog_player_logs`] || []
    ;(window as any)[`__posthog_player_warnings`] = (window as any)[`__posthog_player_warnings`] || []

    const logStores: Record<LogType, any[]> = {
        log: (window as any)[`__posthog_player_logs`],
        warning: (window as any)[`__posthog_player_warnings`],
    }

    const pendingWarningCategories: string[] = []

    const timers: LoggingTimers = {
        log: null,
        warning: null,
    }

    const logger = (type: LogType): ((message?: any, ...optionalParams: any[]) => void) => {
        // NOTE: RRWeb can log _alot_ of warnings,
        // so we debounce the count otherwise we just end up making the performance worse
        // We also don't log the messages directly.
        // Sometimes the sheer size of messages and warnings can cause the browser to crash deserializing it all

        return (...args: any[]): void => {
            logStores[type].push(args)
            counters[type] += 1

            if (type === 'warning') {
                const category = categorizeWarning(args)
                if (!isIgnoredWarning(category)) {
                    pendingWarningCategories.push(category)
                }
            }

            if (!timers[type]) {
                timers[type] = setTimeout(() => {
                    timers[type] = null
                    if (type === 'warning') {
                        onIncrement(logStores[type].length)

                        if (onWarningSummary && pendingWarningCategories.length > 0) {
                            const summary: Record<string, number> = {}
                            for (const category of pendingWarningCategories) {
                                summary[category] = (summary[category] || 0) + 1
                            }
                            pendingWarningCategories.length = 0
                            onWarningSummary(summary)
                        }
                    }

                    counters[type] = 0
                }, 5000)
            }
        }
    }

    return {
        logger: {
            log: logger('log'),
            warn: logger('warning'),
        },
        timers,
    }
}
