import { actions, afterMount, beforeUnmount, kea, listeners, path, reducers, selectors } from 'kea'

import type { hogbotStatusLogicType } from './hogbotStatusLogicType'

const STATUS_POLL_INTERVAL_MS = 5000

export interface HogbotHealthStatus {
    status: 'ok' | 'starting' | 'error'
    busy: 'none' | 'admin' | 'research'
    admin_ready: boolean
    research_running: boolean
    active_signal_id: string | null
}

let _statusPollInterval: ReturnType<typeof setInterval> | null = null

export const hogbotStatusLogic = kea<hogbotStatusLogicType>([
    path(['products', 'hogbot', 'frontend', 'logics', 'hogbotStatusLogic']),
    actions({
        setHealth: (health: HogbotHealthStatus | null) => ({ health }),
        setSandboxReachable: (reachable: boolean) => ({ reachable }),
        startStatusPolling: true,
        stopStatusPolling: true,
    }),
    reducers({
        health: [
            null as HogbotHealthStatus | null,
            {
                setHealth: (_, { health }) => health,
            },
        ],
        sandboxReachable: [
            false as boolean,
            {
                setSandboxReachable: (_, { reachable }) => reachable,
            },
        ],
    }),
    selectors({
        sandboxStatus: [
            (s) => [s.health, s.sandboxReachable],
            (health, sandboxReachable): 'offline' | 'starting' | 'running' => {
                if (!sandboxReachable || !health) {
                    return 'offline'
                }
                if (health.status === 'starting') {
                    return 'starting'
                }
                return 'running'
            },
        ],
        adminStatus: [
            (s) => [s.health, s.sandboxReachable],
            (health, sandboxReachable): 'offline' | 'idle' | 'active' => {
                if (!sandboxReachable || !health) {
                    return 'offline'
                }
                if (!health.admin_ready) {
                    return 'offline'
                }
                return health.busy === 'admin' ? 'active' : 'idle'
            },
        ],
        researchStatus: [
            (s) => [s.health],
            (health): 'offline' | 'idle' | 'active' => {
                if (!health) {
                    return 'offline'
                }
                return health.research_running ? 'active' : 'idle'
            },
        ],
    }),
    listeners(({ actions }) => ({
        startStatusPolling: () => {
            if (_statusPollInterval) {
                clearInterval(_statusPollInterval)
            }
            const poll = async (): Promise<void> => {
                try {
                    const response = await fetch(`/api/projects/@current/hogbot/health/`)
                    const data = await response.json()
                    if (data && typeof data === 'object' && 'admin_ready' in data) {
                        actions.setSandboxReachable(true)
                        actions.setHealth(data as HogbotHealthStatus)
                    } else {
                        actions.setSandboxReachable(false)
                        actions.setHealth(null)
                    }
                } catch {
                    actions.setSandboxReachable(false)
                    actions.setHealth(null)
                }
            }
            void poll()
            _statusPollInterval = setInterval(poll, STATUS_POLL_INTERVAL_MS)
        },
        stopStatusPolling: () => {
            if (_statusPollInterval) {
                clearInterval(_statusPollInterval)
                _statusPollInterval = null
            }
        },
    })),
    afterMount(({ actions }) => {
        actions.startStatusPolling()
    }),
    beforeUnmount(({ actions }) => {
        actions.stopStatusPolling()
    }),
])
