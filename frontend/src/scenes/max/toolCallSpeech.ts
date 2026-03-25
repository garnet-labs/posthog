import api from 'lib/api'

import { stripMarkdown } from '~/lib/utils/stripMarkdown'

/** Human-readable tool id for TTS (snake_case → words). */
export function humanizeToolName(name: string): string {
    return name.replace(/_/g, ' ').replace(/\s+/g, ' ').trim()
}

const MAX_REASON_CHARS = 100

const ARGS_REASON_KEYS = [
    'query',
    'question',
    'search_query',
    'prompt',
    'sql',
    'hogql',
    'path',
    'url',
    'description',
    'title',
    'query_description',
    'viz_description',
    'insight_id',
    'dashboard_id',
    'notebook_id',
] as const

function truncateAtWord(s: string, max: number): string {
    const t = s.trim()
    if (t.length <= max) {
        return t
    }
    const slice = t.slice(0, max)
    const lastSpace = slice.lastIndexOf(' ')
    return (lastSpace > 24 ? slice.slice(0, lastSpace) : slice).trim() + '…'
}

function stripLeadingFiller(s: string): string {
    return s.replace(/^(let me|i'll|i will|i'm going to|i need to)\s+/i, '').trim()
}

/**
 * First sentence or line of assistant text before tool calls, trimmed for TTS (no leading "I'll…" fluff).
 */
export function reasonFromAssistantContent(content: string): string | null {
    const plain = stripMarkdown(content).replace(/\s+/g, ' ').trim()
    if (!plain) {
        return null
    }
    if (plain.startsWith('{') || plain.startsWith('[')) {
        return null
    }
    const first = plain.split(/(?<=[.!?])\s+/)[0]?.trim() ?? plain
    const stripped = stripLeadingFiller(first)
        .replace(/[.!?]+$/g, '')
        .trim()
    if (!stripped) {
        return null
    }
    return truncateAtWord(stripped, MAX_REASON_CHARS)
}

export function reasonFromToolArgs(args: Record<string, unknown>): string | null {
    for (const key of ARGS_REASON_KEYS) {
        const v = args[key]
        if (typeof v === 'string' && v.trim()) {
            const t = v.trim()
            if (!t.startsWith('{') && !t.startsWith('[')) {
                return truncateAtWord(t, MAX_REASON_CHARS)
            }
        }
    }
    for (const v of Object.values(args)) {
        if (typeof v === 'string' && v.trim().length > 3) {
            const t = v.trim()
            if (!t.startsWith('{') && !t.startsWith('[')) {
                return truncateAtWord(t, MAX_REASON_CHARS)
            }
        }
    }
    return null
}

const NESTED_REASON_KEYS = [
    'description',
    'title',
    'query_description',
    'query',
    'viz_description',
    'question',
] as const

function pickStringFromValue(v: unknown, depth: number): string | null {
    if (depth > 2) {
        return null
    }
    if (typeof v === 'string') {
        const t = v.trim()
        if (t.length > 2 && !t.startsWith('{') && !t.startsWith('[')) {
            return truncateAtWord(t, MAX_REASON_CHARS)
        }
        return null
    }
    if (v && typeof v === 'object' && !Array.isArray(v)) {
        const o = v as Record<string, unknown>
        for (const k of NESTED_REASON_KEYS) {
            const inner = o[k]
            const r = pickStringFromValue(inner, depth + 1)
            if (r) {
                return r
            }
        }
    }
    return null
}

/** Best-effort line from contextual ui_payload (result shapes vary by tool). */
export function reasonFromUiPayload(ui: Record<string, unknown>): string | null {
    for (const v of Object.values(ui)) {
        const r = pickStringFromValue(v, 0)
        if (r) {
            return r
        }
    }
    return null
}

function formatToolListHuman(names: string[]): string {
    const human = names.map((n) => humanizeToolName(n))
    if (human.length === 1) {
        return human[0]
    }
    if (human.length === 2) {
        return `${human[0]} and ${human[1]}`
    }
    return `${human.slice(0, -1).join(', ')}, and ${human[human.length - 1]}`
}

export type ToolCallSpeechOptions = {
    /** Assistant message text before the tool call — best source for "why" */
    assistantContent?: string | null
    /** Static / mode tools: args often hold query, question, etc. */
    toolCalls?: Array<{ name: string; args: Record<string, unknown> }>
    /** Contextual tools: payload may include titles or descriptions */
    uiPayload?: Record<string, unknown> | null
}

/**
 * Short voice line: tool name(s) plus a brief reason (assistant text, args, or ui payload).
 */
export function sentenceForToolCalls(names: string[], options?: ToolCallSpeechOptions): string | null {
    const filtered = [...new Set(names.map((n) => n.trim()).filter(Boolean))]
    if (filtered.length === 0) {
        return null
    }
    const toolList = formatToolListHuman(filtered)

    let reason: string | null = null
    if (options?.assistantContent) {
        reason = reasonFromAssistantContent(options.assistantContent)
    }
    if (!reason && options?.toolCalls?.length) {
        for (const tc of options.toolCalls) {
            reason = reasonFromToolArgs(tc.args)
            if (reason) {
                break
            }
        }
    }
    if (!reason && options?.uiPayload) {
        reason = reasonFromUiPayload(options.uiPayload)
    }

    if (reason) {
        const r = reason.endsWith('.') ? reason.slice(0, -1) : reason
        const spoken = r.length > 0 ? r.charAt(0).toLowerCase() + r.slice(1) : r
        return `I'm using ${toolList} to ${spoken}.`
    }
    return `I'm using ${toolList}.`
}

/**
 * @deprecated Prefer {@link sentenceForToolCalls} for optional reason text.
 */
export function sentenceForToolNames(names: string[]): string | null {
    return sentenceForToolCalls(names)
}

function truncateJsonForNarrationPayload(value: unknown, maxStr: number, depth: number): unknown {
    if (depth > 3) {
        return '…'
    }
    if (value === null || value === undefined) {
        return value
    }
    if (typeof value === 'string') {
        return value.length <= maxStr ? value : value.slice(0, maxStr) + '…'
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
        return value
    }
    if (Array.isArray(value)) {
        return value.slice(0, 24).map((x) => truncateJsonForNarrationPayload(x, maxStr, depth + 1))
    }
    if (typeof value === 'object') {
        const obj = value as Record<string, unknown>
        const out: Record<string, unknown> = {}
        let i = 0
        for (const [k, v] of Object.entries(obj)) {
            if (i++ > 48) {
                break
            }
            out[k] = truncateJsonForNarrationPayload(v, maxStr, depth + 1)
        }
        return out
    }
    return String(value).slice(0, maxStr)
}

/** Fast LLM line for voice mode; returns null on failure (caller uses {@link sentenceForToolCalls}). */
export async function fetchLlmToolCallNarrationSentence(params: {
    toolNames: string[]
    assistantContent?: string
    toolCalls?: Array<{ name: string; args: Record<string, unknown> }>
    uiPayload?: Record<string, unknown>
    recentNarrations: string[]
}): Promise<string | null> {
    try {
        const tool_args_by_name =
            params.toolCalls && params.toolCalls.length > 0
                ? (Object.fromEntries(
                      params.toolCalls.map((tc) => [tc.name, truncateJsonForNarrationPayload(tc.args, 400, 0)])
                  ) as Record<string, Record<string, unknown>>)
                : null
        const ui_payload = params.uiPayload
            ? (truncateJsonForNarrationPayload(params.uiPayload, 400, 0) as Record<string, unknown>)
            : null
        const res = await api.conversations.toolCallNarration({
            tool_names: params.toolNames,
            assistant_content: params.assistantContent ?? null,
            tool_args_by_name,
            ui_payload,
            recent_narrations: params.recentNarrations,
        })
        const s = res.sentence?.trim()
        return s || null
    } catch {
        return null
    }
}
