export type HogbotScope = 'admin' | 'research'
export type HogbotBusyState = 'none' | 'admin' | 'research'
export type HogbotStatus = 'starting' | 'running' | 'completed' | 'failed' | 'cancelled'
export type HogbotMethod = '_hogbot/status' | '_hogbot/text' | '_hogbot/result' | '_hogbot/error' | '_hogbot/console'

export interface HogbotJwtPayload {
    team_id: number
    user_id: number
    distinct_id: string
    scope: string
    aud: string
    exp: number
}

export interface HogbotNotificationEvent {
    type: 'notification'
    timestamp: string
    notification: {
        jsonrpc: '2.0'
        method: HogbotMethod
        params: Record<string, unknown>
    }
}

export interface WorkerRuntimeConfig {
    workspacePath: string
    systemPrompt: string
}
