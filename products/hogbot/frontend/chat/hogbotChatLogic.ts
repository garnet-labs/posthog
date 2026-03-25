import { actions, kea, listeners, path, reducers, selectors } from 'kea'
import { loaders } from 'kea-loaders'

// import api from 'lib/api'

import { LogEntry, parseLogs } from 'products/tasks/frontend/lib/parse-logs'

import { MOCK_CHAT_LOG_ENTRIES } from '../__mocks__/chatMocks'
import type { hogbotChatLogicType } from './hogbotChatLogicType'

/** Groups consecutive log entries into chat blocks for rendering. */
export interface ChatBlock {
    id: string
    type: 'message' | 'thinking'
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
        appendEntry: (entry: LogEntry) => ({ entry }),
        setInputValue: (inputValue: string) => ({ inputValue }),
        setLogs: (logs: string) => ({ logs }),
        setStreamEntries: (entries: LogEntry[]) => ({ entries }),
    }),
    loaders({
        logs: [
            '' as string,
            {
                loadLogs: async (): Promise<string> => {
                    // TODO: Replace with API call when backend is ready
                    // Admin agent logs live at a known URL — no session/run ID needed
                    // const response = await api.get(
                    //     `api/projects/@current/hogbot/admin/logs/`,
                    //     { responseType: 'text' }
                    // )
                    // return response
                    return ''
                },
            },
        ],
    }),
    reducers({
        logs: {
            setLogs: (_, { logs }) => logs,
        },
        streamEntries: [
            [] as LogEntry[],
            {
                setStreamEntries: (_, { entries }) => entries,
                appendEntry: (state, { entry }) => [...state, entry],
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
                appendEntry: () => false,
            },
        ],
    }),
    selectors({
        entries: [
            (s) => [s.logs, s.streamEntries],
            (logs, streamEntries): LogEntry[] => {
                // Use stream entries when available, otherwise fall back to parsed S3 logs
                if (streamEntries.length > 0) {
                    return streamEntries
                }
                if (logs) {
                    return parseLogs(logs)
                }
                // Mock data while backend isn't ready
                return MOCK_CHAT_LOG_ENTRIES
            },
        ],
        chatBlocks: [
            (s) => [s.entries],
            (entries): ChatBlock[] => groupIntoChatBlocks(entries),
        ],
    }),
    listeners(({ actions }) => ({
        sendMessage: async ({ content }) => {
            const userEntry: LogEntry = {
                id: `log-user-${Date.now()}`,
                type: 'user',
                timestamp: new Date().toISOString(),
                message: content,
            }
            actions.appendEntry(userEntry)

            // TODO: Replace with API call when backend is ready
            // Posts to the admin agent's message endpoint
            // await api.create(`api/projects/@current/hogbot/admin/messages/`, { content })
            // Agent response will arrive via SSE stream at /hogbot/admin/stream/

            // Simulate agent response for now
            await new Promise((resolve) => setTimeout(resolve, 1000))
            const agentEntry: LogEntry = {
                id: `log-agent-${Date.now()}`,
                type: 'agent',
                timestamp: new Date().toISOString(),
                message:
                    "I've received your message and I'm working on it. This is a mock response — the backend isn't connected yet.",
            }
            actions.appendEntry(agentEntry)
        },
    })),
])
