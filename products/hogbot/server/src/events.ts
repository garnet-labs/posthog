import type { HogbotMethod, HogbotNotificationEvent, HogbotScope, HogbotStatus } from './types'

function createEvent(method: HogbotMethod, params: Record<string, unknown>): HogbotNotificationEvent {
    return {
        type: 'notification',
        timestamp: new Date().toISOString(),
        notification: {
            jsonrpc: '2.0',
            method,
            params,
        },
    }
}

export function statusEvent(
    scope: HogbotScope,
    teamId: number,
    status: HogbotStatus,
    options: { signalId?: string; message?: string } = {}
): HogbotNotificationEvent {
    return createEvent('_hogbot/status', {
        scope,
        team_id: teamId,
        signal_id: options.signalId,
        status,
        message: options.message,
    })
}

export function textEvent(
    scope: HogbotScope,
    teamId: number,
    text: string,
    options: { signalId?: string; role?: 'assistant' | 'system' } = {}
): HogbotNotificationEvent {
    return createEvent('_hogbot/text', {
        scope,
        team_id: teamId,
        signal_id: options.signalId,
        role: options.role ?? 'assistant',
        text,
    })
}

export function resultEvent(
    scope: HogbotScope,
    teamId: number,
    output: string,
    options: { signalId?: string } = {}
): HogbotNotificationEvent {
    return createEvent('_hogbot/result', {
        scope,
        team_id: teamId,
        signal_id: options.signalId,
        output,
    })
}

export function errorEvent(
    scope: HogbotScope,
    teamId: number,
    message: string,
    options: { signalId?: string } = {}
): HogbotNotificationEvent {
    return createEvent('_hogbot/error', {
        scope,
        team_id: teamId,
        signal_id: options.signalId,
        message,
    })
}

export function consoleEvent(
    scope: HogbotScope,
    teamId: number,
    level: 'debug' | 'info' | 'warn' | 'error',
    message: string,
    options: { signalId?: string } = {}
): HogbotNotificationEvent {
    return createEvent('_hogbot/console', {
        scope,
        team_id: teamId,
        signal_id: options.signalId,
        level,
        message,
    })
}

export function toolCallEvent(
    scope: HogbotScope,
    teamId: number,
    toolName: string,
    toolCallId: string,
    status: 'running' | 'completed' | 'error',
    options: { signalId?: string; input?: Record<string, unknown>; result?: unknown } = {}
): HogbotNotificationEvent {
    return createEvent('_hogbot/tool_call', {
        scope,
        team_id: teamId,
        signal_id: options.signalId,
        tool_name: toolName,
        tool_call_id: toolCallId,
        status,
        input: options.input,
        result: options.result,
    })
}

export function thinkingEvent(
    scope: HogbotScope,
    teamId: number,
    text: string,
    options: { signalId?: string } = {}
): HogbotNotificationEvent {
    return createEvent('_hogbot/thinking', {
        scope,
        team_id: teamId,
        signal_id: options.signalId,
        text,
    })
}
