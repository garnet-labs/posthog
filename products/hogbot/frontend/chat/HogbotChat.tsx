import { useActions, useValues } from 'kea'
import { useEffect, useRef } from 'react'

import { LemonButton, Spinner } from '@posthog/lemon-ui'

import { LemonTextArea } from 'lib/lemon-ui/LemonTextArea/LemonTextArea'

import { ChatMessage } from './ChatMessage'
import { hogbotChatLogic } from './hogbotChatLogic'
import { ThinkingSection } from './ThinkingSection'

export function HogbotChat(): JSX.Element {
    const { chatBlocks, logsLoading, inputValue, sending } = useValues(hogbotChatLogic)
    const { sendMessage, setInputValue } = useActions(hogbotChatLogic)
    const messagesEndRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [chatBlocks])

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
                {logsLoading ? (
                    <div className="flex items-center justify-center h-full">
                        <Spinner className="text-2xl" />
                    </div>
                ) : chatBlocks.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-muted">
                        No messages yet. Start a conversation with Hogbot!
                    </div>
                ) : (
                    <>
                        {chatBlocks.map((block) =>
                            block.type === 'message' ? (
                                <ChatMessage key={block.id} entry={block.entries[0]} />
                            ) : block.type === 'system' ? (
                                <div key={block.id} className="flex justify-center my-3">
                                    <span className="text-xs text-muted bg-surface-primary border rounded-full px-3 py-1">
                                        {block.entries[0]?.message}
                                    </span>
                                </div>
                            ) : (
                                <ThinkingSection key={block.id} entries={block.entries} />
                            )
                        )}
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
