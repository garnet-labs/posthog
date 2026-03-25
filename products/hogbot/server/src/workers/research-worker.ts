import type { Query, SDKMessage } from '@anthropic-ai/claude-agent-sdk'

import type { ResearchParentMessage, ResearchWorkerMessage } from '../ipc'
import { RESEARCH_SYSTEM_PROMPT } from '../prompts'

function send(message: ResearchWorkerMessage): void {
    if (process.send) {
        process.send(message)
    }
}

function emitEvent(
    method: '_hogbot/status' | '_hogbot/text' | '_hogbot/result' | '_hogbot/error' | '_hogbot/console',
    params: Record<string, unknown>
): void {
    send({ type: 'event', method, params })
}

function getRequiredEnv(name: string): string {
    const value = process.env[name]
    if (!value) {
        throw new Error(`Missing required environment variable ${name}`)
    }
    return value
}

async function runResearch(signalId: string, prompt: string): Promise<void> {
    const workspacePath = getRequiredEnv('HOGBOT_WORKSPACE_PATH')
    const sdk = require('@anthropic-ai/claude-agent-sdk') as {
        query: (typeof import('@anthropic-ai/claude-agent-sdk'))['query']
    }
    const query: Query = sdk.query({
        prompt,
        options: {
            cwd: workspacePath,
            env: process.env,
            tools: { type: 'preset', preset: 'claude_code' },
            systemPrompt: { type: 'preset', preset: 'claude_code', append: RESEARCH_SYSTEM_PROMPT },
            permissionMode: 'bypassPermissions',
            allowDangerouslySkipPermissions: true,
        },
    })

    emitEvent('_hogbot/status', { status: 'running' })

    try {
        for await (const message of query) {
            handleMessage(message, signalId)
        }
    } finally {
        query.close()
    }
}

function handleMessage(message: SDKMessage, signalId: string): void {
    if (message.type === 'auth_status') {
        emitEvent('_hogbot/console', {
            level: message.error ? 'error' : 'info',
            message: message.error ?? (message.output || []).join('\n'),
        })
        return
    }

    if (message.type !== 'result') {
        return
    }

    if (message.subtype === 'success' && typeof message.result === 'string') {
        emitEvent('_hogbot/text', { role: 'assistant', text: message.result })
        emitEvent('_hogbot/result', { output: message.result })
        emitEvent('_hogbot/status', { status: 'completed' })
        send({ type: 'done', signalId, output: message.result })
        process.exit(0)
        return
    }

    const errorText =
        Array.isArray(message.errors) && message.errors.length > 0
            ? message.errors.join('\n')
            : 'Claude execution failed'
    emitEvent('_hogbot/error', { message: errorText })
    emitEvent('_hogbot/status', { status: 'failed', message: errorText })
    send({ type: 'failed', signalId, error: errorText })
    process.exit(1)
}

send({ type: 'ready' })

process.on('message', (message: ResearchParentMessage) => {
    if (message.type === 'shutdown') {
        process.exit(0)
        return
    }

    void runResearch(message.signalId, message.prompt).catch((error) => {
        const errorText = error instanceof Error ? error.message : String(error)
        emitEvent('_hogbot/error', { message: errorText })
        emitEvent('_hogbot/status', { status: 'failed', message: errorText })
        send({ type: 'failed', signalId: message.signalId, error: errorText })
        process.exit(1)
    })
})
