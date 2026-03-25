import { ProfilePicture } from '@posthog/lemon-ui'

import { LemonMarkdown } from 'lib/lemon-ui/LemonMarkdown'

import { LogEntry } from 'products/tasks/frontend/lib/parse-logs'

export interface ChatMessageProps {
    entry: LogEntry
}

export function ChatMessage({ entry }: ChatMessageProps): JSX.Element {
    const isUser = entry.type === 'user'

    return (
        <div className={`flex ${isUser ? 'flex-row-reverse ml-10' : 'mr-10'} mb-4`}>
            <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
                <div className="shrink-0 mt-1">
                    <ProfilePicture size="md" type={isUser ? 'person' : 'bot'} name={isUser ? 'You' : 'Hogbot'} />
                </div>
                <div className="flex flex-col min-w-0">
                    <div className={`flex items-center gap-2 mb-1 ${isUser ? 'flex-row-reverse' : ''}`}>
                        <span className="text-xs font-semibold">{isUser ? 'You' : 'Hogbot'}</span>
                        {entry.timestamp && (
                            <span className="text-xs text-muted-alt">
                                {new Date(entry.timestamp).toLocaleTimeString()}
                            </span>
                        )}
                    </div>
                    <div
                        className={`border py-2 px-3 rounded-lg ${
                            isUser ? 'bg-primary-alt-highlight border-primary-alt' : 'bg-surface-primary'
                        }`}
                    >
                        <LemonMarkdown className="text-sm">{entry.message || ''}</LemonMarkdown>
                    </div>
                </div>
            </div>
        </div>
    )
}
