import { useState } from 'react'

import { IconChevronRight, IconGear } from '@posthog/icons'

import { LogEntry } from 'products/tasks/frontend/lib/parse-logs'
import { ConsoleLogEntry } from 'products/tasks/frontend/components/session/ConsoleLogEntry'
import { ToolCallEntry } from 'products/tasks/frontend/components/session/ToolCallEntry'

export interface ThinkingSectionProps {
    entries: LogEntry[]
}

function ThinkingEntry({ entry }: { entry: LogEntry }): JSX.Element | null {
    switch (entry.type) {
        case 'tool':
            return (
                <ToolCallEntry
                    toolName={entry.toolName || 'unknown'}
                    status={entry.toolStatus || 'pending'}
                    args={entry.toolArgs}
                    result={entry.toolResult}
                    timestamp={entry.timestamp}
                />
            )
        case 'console':
            return (
                <ConsoleLogEntry
                    level={entry.level || 'info'}
                    message={entry.message || ''}
                    timestamp={entry.timestamp}
                />
            )
        case 'system':
            return (
                <div className="flex items-center gap-2 py-1">
                    {entry.timestamp && (
                        <span className="text-xs text-muted">{new Date(entry.timestamp).toLocaleTimeString()}</span>
                    )}
                    <span className="text-xs text-muted italic">{entry.message}</span>
                </div>
            )
        case 'raw':
            return <div className="py-0.5 text-xs font-mono text-muted break-all">{entry.raw}</div>
        default:
            return null
    }
}

export function ThinkingSection({ entries }: ThinkingSectionProps): JSX.Element {
    const [isOpen, setIsOpen] = useState(false)

    const toolCount = entries.filter((e) => e.type === 'tool').length
    const summary = toolCount > 0 ? `${toolCount} tool call${toolCount !== 1 ? 's' : ''}` : `${entries.length} step${entries.length !== 1 ? 's' : ''}`

    return (
        <div className="my-2 ml-10">
            <button
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center gap-1.5 text-xs text-muted hover:text-default cursor-pointer py-1"
            >
                <IconChevronRight
                    className={`transition-transform ${isOpen ? 'rotate-90' : ''}`}
                    fontSize="12"
                />
                <IconGear className="text-muted" fontSize="12" />
                <span>Thinking ({summary})</span>
            </button>
            {isOpen && (
                <div className="ml-4 border-l border-muted pl-3 mt-1">
                    {entries.map((entry) => (
                        <ThinkingEntry key={entry.id} entry={entry} />
                    ))}
                </div>
            )}
        </div>
    )
}
