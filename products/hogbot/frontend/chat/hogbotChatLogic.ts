import { actions, afterMount, beforeUnmount, kea, listeners, path, reducers, selectors } from 'kea'

import api from 'lib/api'

import { LogEntry, parseLogs } from 'products/tasks/frontend/lib/parse-logs'

import type { hogbotChatLogicType } from './hogbotChatLogicType'

const POLL_INTERVAL_MS = 3000

// Module-level so it survives HMR — each hot reload creates a new kea logic
// with a fresh cache, orphaning the old setInterval. Storing it here lets
// startPolling always clear the previous interval.
let _pollInterval: ReturnType<typeof setInterval> | null = null

/** Groups consecutive log entries into chat blocks for rendering. */
export interface ChatBlock {
    id: string
    type: 'message' | 'thinking' | 'system'
    entries: LogEntry[]
}

function groupIntoChatBlocks(entries: LogEntry[]): ChatBlock[] {
    const blocks: ChatBlock[] = []
    let currentThinking: LogEntry[] = []

    const flushThinking = (): void => {
        if (currentThinking.length > 0) {
            blocks.push({
                id: `thinking-${currentThinking[0].id}`,
                type: 'thinking',
                entries: [...currentThinking],
            })
            currentThinking = []
        }
    }

    for (const entry of entries) {
        if (entry.type === 'user' || entry.type === 'agent') {
            flushThinking()
            blocks.push({
                id: entry.id,
                type: 'message',
                entries: [entry],
            })
        } else if (entry.type === 'system') {
            flushThinking()
            blocks.push({
                id: entry.id,
                type: 'system',
                entries: [entry],
            })
        } else {
            currentThinking.push(entry)
        }
    }
    flushThinking()

    return blocks
}

export const hogbotChatLogic = kea<hogbotChatLogicType>([
    path(['products', 'hogbot', 'frontend', 'chat', 'hogbotChatLogic']),
    actions({
        sendMessage: (content: string) => ({ content }),
        setInputValue: (inputValue: string) => ({ inputValue }),
        setLogs: (logs: string) => ({ logs }),
        startPolling: true,
        stopPolling: true,
    }),
    reducers({
        logs: [
            '' as string,
            {
                // Only update when content actually changes
                setLogs: (state, { logs }) => (logs === state ? state : logs),
            },
        ],
        logsLoading: [
            true as boolean,
            {
                setLogs: () => false,
            },
        ],
        inputValue: [
            '',
            {
                setInputValue: (_, { inputValue }) => inputValue,
                sendMessage: () => '',
            },
        ],
        sending: [
            false,
            {
                sendMessage: () => true,
                setLogs: () => false,
            },
        ],
    }),
    selectors({
        entries: [
            (s) => [s.logs],
            (logs): LogEntry[] => {
                if (logs) {
                    return parseLogs(logs)
                }
                return []
            },
        ],
        chatBlocks: [(s) => [s.entries], (entries): ChatBlock[] => groupIntoChatBlocks(entries)],
    }),
    listeners(({ actions }) => ({
        startPolling: () => {
            if (_pollInterval) {
                clearInterval(_pollInterval)
            }
            const poll = async (): Promise<void> => {
                try {
                    const response = await api.getResponse(`api/projects/@current/hogbot/admin/logs/`)
                    const text = await response.text()
                    actions.setLogs(text)
                } catch {
                    // Silently ignore poll errors
                }
            }
            _pollInterval = setInterval(poll, POLL_INTERVAL_MS)
        },
        stopPolling: () => {
            if (_pollInterval) {
                clearInterval(_pollInterval)
                _pollInterval = null
            }
        },
        sendMessage: async ({ content }) => {
            try {
                await api.create(`api/projects/@current/hogbot/send-message/`, {
                    type: 'user_message',
                    content,
                })
            } catch {
                // 503 is expected when sandbox isn't running yet
            }
            // Trigger an immediate poll to pick up the response faster
            try {
                const response = await api.getResponse(`api/projects/@current/hogbot/admin/logs/`)
                const text = await response.text()
                actions.setLogs(text)
            } catch {
                // ignore
            }
        },
    })),
    afterMount(({ actions }) => {
        // Initial load
        const load = async (): Promise<void> => {
            try {
                const response = await api.getResponse(`api/projects/@current/hogbot/admin/logs/`)
                const text = await response.text()
                actions.setLogs(text)
            } catch {
                actions.setLogs('')
            }
        }
        void load()
        actions.startPolling()
    }),
    beforeUnmount(({ actions }) => {
        actions.stopPolling()
    }),
])
