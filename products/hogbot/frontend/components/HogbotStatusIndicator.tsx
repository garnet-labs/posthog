import { useValues } from 'kea'

import { Tooltip } from '@posthog/lemon-ui'

import { hogbotStatusLogic } from '../logics/hogbotStatusLogic'

type StatusColor = 'green' | 'yellow' | 'red' | 'gray'

function statusColor(status: string): StatusColor {
    switch (status) {
        case 'running':
        case 'active':
            return 'green'
        case 'starting':
            return 'yellow'
        case 'idle':
            return 'gray'
        default:
            return 'red'
    }
}

const COLOR_CLASSES: Record<StatusColor, string> = {
    green: 'bg-success',
    yellow: 'bg-warning',
    red: 'bg-danger',
    gray: 'bg-muted-alt',
}

function StatusDot({ color, pulse }: { color: StatusColor; pulse?: boolean }): JSX.Element {
    return (
        <span className="relative flex h-2.5 w-2.5">
            {pulse && (
                <span
                    className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-50 ${COLOR_CLASSES[color]}`}
                />
            )}
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${COLOR_CLASSES[color]}`} />
        </span>
    )
}

function StatusItem({ label, status }: { label: string; status: string }): JSX.Element {
    const color = statusColor(status)
    return (
        <Tooltip title={`${label}: ${status}`}>
            <div className="flex items-center gap-1.5">
                <StatusDot color={color} pulse={color === 'green' || color === 'yellow'} />
                <span className="text-xs text-muted">{label}</span>
            </div>
        </Tooltip>
    )
}

export function HogbotStatusIndicator(): JSX.Element {
    const { sandboxStatus, adminStatus, researchStatus } = useValues(hogbotStatusLogic)

    return (
        <div className="flex items-center gap-4">
            <StatusItem label="Sandbox" status={sandboxStatus} />
            <StatusItem label="Admin" status={adminStatus} />
            <StatusItem label="Research" status={researchStatus} />
        </div>
    )
}
