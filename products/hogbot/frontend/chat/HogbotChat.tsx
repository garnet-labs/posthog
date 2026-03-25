import { useActions, useValues } from 'kea'
import { useEffect, useRef } from 'react'

import { LemonButton, Spinner } from '@posthog/lemon-ui'

import { LemonTextArea } from 'lib/lemon-ui/LemonTextArea/LemonTextArea'

import { ChatMessage } from './ChatMessage'
import { hogbotChatLogic } from './hogbotChatLogic'

export function HogbotChat(): JSX.Element {
    const { messages, messagesLoading, inputValue, sending } = useValues(hogbotChatLogic)
    const { loadMessages, sendMessage, setInputValue } = useActions(hogbotChatLogic)
    const messagesEndRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        loadMessages()
    }, [])

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages])

    const handleSend = (): void => {
        const trimmed = inputValue.trim()
        if (trimmed) {
            sendMessage(trimmed)
        }
    }

    const handleKeyDown = (e: React.KeyboardEvent): void => {
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
            e.preventDefault()
            handleSend()
        }
    }

    return (
        <div className="flex flex-col border rounded-lg overflow-hidden h-[calc(100vh-12rem)]">
            <div className="flex-1 overflow-y-auto p-4">
                {messagesLoading ? (
                    <div className="flex items-center justify-center h-full">
                        <Spinner className="text-2xl" />
                    </div>
                ) : messages.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-muted">
                        No messages yet. Start a conversation with Hogbot!
                    </div>
                ) : (
                    <>
                        {messages.map((message) => (
                            <ChatMessage key={message.id} message={message} />
                        ))}
                        <div ref={messagesEndRef} />
                    </>
                )}
            </div>
            <div className="border-t p-3">
                <div onKeyDown={handleKeyDown}>
                    <LemonTextArea
                        placeholder="Message Hogbot... (Cmd+Enter to send)"
                        value={inputValue}
                        onChange={(value) => setInputValue(value)}
                        minRows={2}
                        maxRows={6}
                        disabled={sending}
                    />
                </div>
                <div className="flex justify-end mt-2">
                    <LemonButton
                        type="primary"
                        onClick={handleSend}
                        loading={sending}
                        disabledReason={!inputValue.trim() ? 'Type a message first' : undefined}
                    >
                        Send
                    </LemonButton>
                </div>
            </div>
        </div>
    )
}
