import type { Query, SDKMessage, SDKUserMessage } from '@anthropic-ai/claude-agent-sdk'
import { randomBytes } from 'crypto'

import type { AdminParentMessage, AdminWorkerMessage } from '../ipc'
import { getPostHogMcpServersFromEnv } from '../mcp'
import { ADMIN_SYSTEM_PROMPT } from '../prompts'
import { Pushable } from '../pushable'

function send(message: AdminWorkerMessage): void {
    if (process.send) {
        process.send(message)
    }
}

function emitEvent(
    method:
        | '_hogbot/status'
        | '_hogbot/text'
        | '_hogbot/result'
        | '_hogbot/error'
        | '_hogbot/console'
        | '_hogbot/tool_call'
        | '_hogbot/thinking',
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

async function main(): Promise<void> {
    const workspacePath = getRequiredEnv('HOGBOT_WORKSPACE_PATH')
    const sessionId = randomBytes(16).toString('hex')
    const input = new Pushable<SDKUserMessage>()

    const sdk = require('@anthropic-ai/claude-agent-sdk') as {
        query: (typeof import('@anthropic-ai/claude-agent-sdk'))['query']
    }
    const mcpServers = getPostHogMcpServersFromEnv(process.env)
    const query: Query = sdk.query({
        prompt: input,
        options: {
            cwd: workspacePath,
            env: process.env,
            tools: { type: 'preset', preset: 'claude_code' },
            mcpServers,
            systemPrompt: { type: 'preset', preset: 'claude_code', append: ADMIN_SYSTEM_PROMPT },
            permissionMode: 'bypassPermissions',
            allowDangerouslySkipPermissions: true,
        },
    })

    let activeRequestId: string | null = null

    const consumeMessages = async (): Promise<void> => {
        for await (const message of query) {
            await handleSdkMessage(
                message,
                () => activeRequestId,
                (value) => {
                    activeRequestId = value
                }
            )
        }
    }

    const handleSdkMessage = async (
        message: SDKMessage,
        getRequestId: () => string | null,
        setRequestId: (value: string | null) => void
    ): Promise<void> => {
        if (message.type === 'auth_status') {
            emitEvent('_hogbot/console', {
                level: message.error ? 'error' : 'info',
                message: message.error ?? (message.output || []).join('\n'),
            })
            return
        }

        if (message.type === 'assistant') {
            emitAssistantContentBlocks(message.message)
            return
        }

        if (message.type !== 'result') {
            return
        }

        const requestId = getRequestId()
        if (!requestId) {
            return
        }

        if (message.subtype === 'success' && typeof message.result === 'string') {
            emitEvent('_hogbot/text', { role: 'assistant', text: message.result })
            emitEvent('_hogbot/result', { output: message.result })
            emitEvent('_hogbot/status', { status: 'completed' })
            send({ type: 'response', requestId, response: message.result })
            setRequestId(null)
            return
        }

        const errorText =
            Array.isArray(message.errors) && message.errors.length > 0
                ? message.errors.join('\n')
                : 'Claude execution failed'
        emitEvent('_hogbot/error', { message: errorText })
        emitEvent('_hogbot/status', { status: 'failed', message: errorText })
        send({ type: 'request_error', requestId, error: errorText })
        setRequestId(null)
    }

    function emitAssistantContentBlocks(msg: unknown): void {
        if (!msg || typeof msg !== 'object') {
            return
        }
        const content = (msg as Record<string, unknown>).content
        if (!Array.isArray(content)) {
            return
        }
        for (const block of content) {
            if (!block || typeof block !== 'object') {
                continue
            }
            const b = block as Record<string, unknown>
            if (b.type === 'thinking' && typeof b.thinking === 'string') {
                emitEvent('_hogbot/thinking', { text: b.thinking })
            } else if (b.type === 'tool_use') {
                emitEvent('_hogbot/tool_call', {
                    tool_name: (b.name as string) || 'unknown',
                    tool_call_id: (b.id as string) || '',
                    status: 'running',
                    input: b.input as Record<string, unknown> | undefined,
                })
            } else if (b.type === 'tool_result') {
                emitEvent('_hogbot/tool_call', {
                    tool_name: '',
                    tool_call_id: (b.tool_use_id as string) || '',
                    status: b.is_error ? 'error' : 'completed',
                    result: b.content,
                })
            }
        }
    }

    void consumeMessages().catch((error) => {
        send({ type: 'fatal', error: error instanceof Error ? error.message : String(error) })
    })

    await query.initializationResult()
    send({ type: 'ready', sessionId })

    process.on('message', async (message: AdminParentMessage) => {
        try {
            if (message.type === 'send_message') {
                if (activeRequestId) {
                    send({ type: 'request_error', requestId: message.requestId, error: 'Admin worker is already busy' })
                    return
                }
                activeRequestId = message.requestId
                emitEvent('_hogbot/status', { status: 'running' })
                input.push({
                    type: 'user',
                    message: {
                        role: 'user',
                        content: [{ type: 'text', text: message.content }],
                    },
                    parent_tool_use_id: null,
                    session_id: sessionId,
                })
                return
            }

            if (message.type === 'cancel') {
                if (!activeRequestId) {
                    send({ type: 'cancelled' })
                    return
                }
                const requestId = activeRequestId
                activeRequestId = null
                await query.interrupt()
                emitEvent('_hogbot/status', { status: 'cancelled' })
                send({ type: 'cancelled', requestId })
                return
            }

            query.close()
            process.exit(0)
        } catch (error) {
            send({ type: 'fatal', error: error instanceof Error ? error.message : String(error) })
        }
    })
}

void main().catch((error) => {
    send({ type: 'fatal', error: error instanceof Error ? error.message : String(error) })
    process.exit(1)
})
