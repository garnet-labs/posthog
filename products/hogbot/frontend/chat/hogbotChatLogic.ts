import { actions, kea, listeners, path, reducers } from 'kea'
import { loaders } from 'kea-loaders'

// import api from 'lib/api'

import { MOCK_CHAT_MESSAGES } from '../__mocks__/chatMocks'
import type { hogbotChatLogicType } from './hogbotChatLogicType'
import { HogbotMessage, MessageRole, MessageType } from '../types'

export const hogbotChatLogic = kea<hogbotChatLogicType>([
    path(['products', 'hogbot', 'frontend', 'chat', 'hogbotChatLogic']),
    actions({
        sendMessage: (content: string) => ({ content }),
        appendMessage: (message: HogbotMessage) => ({ message }),
        setInputValue: (inputValue: string) => ({ inputValue }),
    }),
    loaders({
        messages: [
            [] as HogbotMessage[],
            {
                loadMessages: async (): Promise<HogbotMessage[]> => {
                    // TODO: Replace with API call when backend is ready
                    // const response = await api.get(`api/projects/@current/hogbot/messages/`)
                    // return response.results
                    return MOCK_CHAT_MESSAGES
                },
            },
        ],
    }),
    reducers({
        messages: {
            appendMessage: (state, { message }) => [...state, message],
        },
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
                appendMessage: () => false,
            },
        ],
    }),
    listeners(({ actions }) => ({
        sendMessage: async ({ content }) => {
            const userMessage: HogbotMessage = {
                id: `msg-${Date.now()}`,
                role: MessageRole.USER,
                type: MessageType.TEXT,
                content,
                created_at: new Date().toISOString(),
            }
            actions.appendMessage(userMessage)

            // TODO: Replace with API call when backend is ready
            // const response = await api.create(`api/projects/@current/hogbot/messages/`, { content })
            // actions.appendMessage(response)

            // Simulate agent response for now
            await new Promise((resolve) => setTimeout(resolve, 1000))
            const agentMessage: HogbotMessage = {
                id: `msg-${Date.now() + 1}`,
                role: MessageRole.AGENT,
                type: MessageType.TEXT,
                content: "I've received your message and I'm working on it. This is a mock response — the backend isn't connected yet.",
                created_at: new Date().toISOString(),
            }
            actions.appendMessage(agentMessage)
        },
    })),
])
