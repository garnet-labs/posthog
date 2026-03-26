import type { Query, SDKMessage } from '@anthropic-ai/claude-agent-sdk'
import { mkdir, writeFile } from 'fs/promises'
import path from 'path'

import type { ResearchParentMessage, ResearchWorkerMessage } from '../ipc'
import { getPostHogMcpServersFromEnv } from '../mcp'
import { RESEARCH_SYSTEM_PROMPT } from '../prompts'

function send(message: ResearchWorkerMessage): void {
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

function getRequiredEnv(name: string): string {
    const value = process.env[name]
    if (!value) {
        throw new Error(`Missing required environment variable ${name}`)
    }
    return value
}

function slugifySignalId(signalId: string): string {
    const slug = signalId.trim().replace(/[^A-Za-z0-9._-]+/g, '-')
    return slug || 'research'
}

async function writeResearchMarkdown(
    workspacePath: string,
    signalId: string,
    prompt: string,
    output: string
): Promise<string> {
    const researchDir = path.join(workspacePath, 'research')
    await mkdir(researchDir, { recursive: true })

    const fileName = `${slugifySignalId(signalId)}.md`
    const filePath = path.join(researchDir, fileName)
    const markdown = [`# Research: ${signalId}`, '', `Prompt: ${prompt}`, '', output.trim()].join('\n')
    await writeFile(filePath, markdown.endsWith('\n') ? markdown : `${markdown}\n`, 'utf-8')
    return filePath
}

async function runResearch(signalId: string, prompt: string): Promise<void> {
    const workspacePath = getRequiredEnv('HOGBOT_WORKSPACE_PATH')
    const sdk = require('@anthropic-ai/claude-agent-sdk') as {
        query: (typeof import('@anthropic-ai/claude-agent-sdk'))['query']
    }
    const mcpServers = getPostHogMcpServersFromEnv(process.env)
    const query: Query = sdk.query({
        prompt,
        options: {
            cwd: workspacePath,
            env: process.env,
            tools: { type: 'preset', preset: 'claude_code' },
            mcpServers,
            systemPrompt: { type: 'preset', preset: 'claude_code', append: RESEARCH_SYSTEM_PROMPT },
            permissionMode: 'bypassPermissions',
            allowDangerouslySkipPermissions: true,
        },
    })

    emitEvent('_hogbot/status', { status: 'running' })

    try {
        for await (const message of query) {
            await handleMessage(message, signalId, prompt, workspacePath)
        }
    } finally {
        query.close()
    }
}

async function handleMessage(
    message: SDKMessage,
    signalId: string,
    prompt: string,
    workspacePath: string
): Promise<void> {
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

    if (message.subtype === 'success' && typeof message.result === 'string') {
        const outputPath = await writeResearchMarkdown(workspacePath, signalId, prompt, message.result)
        emitEvent('_hogbot/text', { role: 'assistant', text: message.result })
        emitEvent('_hogbot/console', {
            level: 'info',
            message: `Wrote research output to ${path.relative(workspacePath, outputPath)}`,
        })
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
