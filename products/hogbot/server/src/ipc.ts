import type { HogbotMethod } from './types'

export type AdminParentMessage =
    | { type: 'send_message'; requestId: string; content: string }
    | { type: 'cancel'; requestId?: string }
    | { type: 'shutdown' }

export type ResearchParentMessage = { type: 'start'; signalId: string; prompt: string } | { type: 'shutdown' }

export type WorkerEventMessage = { type: 'event'; method: HogbotMethod; params: Record<string, unknown> }

export type AdminWorkerMessage =
    | { type: 'ready'; sessionId: string }
    | WorkerEventMessage
    | { type: 'response'; requestId: string; response: string }
    | { type: 'request_error'; requestId: string; error: string }
    | { type: 'cancelled'; requestId?: string }
    | { type: 'fatal'; error: string }

export type ResearchWorkerMessage =
    | { type: 'ready' }
    | WorkerEventMessage
    | { type: 'done'; signalId: string; output: string }
    | { type: 'failed'; signalId: string; error: string }
    | { type: 'fatal'; error: string }
