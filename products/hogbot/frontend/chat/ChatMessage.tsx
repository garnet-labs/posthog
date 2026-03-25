import { IconSparkles } from '@posthog/icons'
import { ProfilePicture, Tooltip } from '@posthog/lemon-ui'

import { TZLabel } from 'lib/components/TZLabel'
import { LemonMarkdown } from 'lib/lemon-ui/LemonMarkdown'

import { HogbotMessage, MessageRole, MessageType } from '../types'

export interface ChatMessageProps {
    message: HogbotMessage
}

export function ChatMessage({ message }: ChatMessageProps): JSX.Element {
    const isUser = message.role === MessageRole.USER
    const isProactive = message.type === MessageType.PROACTIVE

    return (
        <div className={`flex ${isUser ? 'flex-row-reverse ml-10' : 'mr-10'} mb-4`}>
            <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
                <div className="shrink-0 mt-1">
                    <ProfilePicture size="md" type={isUser ? 'person' : 'bot'} name={isUser ? 'You' : 'Hogbot'} />
                </div>
                <div className="flex flex-col min-w-0">
                    <div className={`flex items-center gap-2 mb-1 ${isUser ? 'flex-row-reverse' : ''}`}>
                        <span className="text-xs font-semibold">{isUser ? 'You' : 'Hogbot'}</span>
                        {isProactive && (
                            <Tooltip title="Hogbot sent this message proactively based on its analysis">
                                <span className="inline-flex items-center gap-0.5 text-xs text-primary-alt bg-primary-alt-highlight px-1.5 py-0.5 rounded">
                                    <IconSparkles className="text-xs" />
                                    Proactive
                                </span>
                            </Tooltip>
                        )}
                        <span className="text-xs text-muted-alt">
                            <TZLabel time={message.created_at} />
                        </span>
                    </div>
                    <div
                        className={`border py-2 px-3 rounded-lg ${
                            isUser
                                ? 'bg-primary-alt-highlight border-primary-alt'
                                : isProactive
                                  ? 'bg-warning-highlight border-warning'
                                  : 'bg-surface-primary'
                        }`}
                    >
                        <LemonMarkdown className="text-sm">{message.content}</LemonMarkdown>
                    </div>
                </div>
            </div>
        </div>
    )
}
