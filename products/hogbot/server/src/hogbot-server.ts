import { serve, type ServerType } from '@hono/node-server'
import { fork, type ChildProcess } from 'child_process'
import { randomBytes } from 'crypto'
import { mkdir, writeFile } from 'fs/promises'
import { Hono } from 'hono'
import { streamSSE } from 'hono/streaming'
import type { AddressInfo } from 'net'
import path from 'path'

import { consoleEvent, errorEvent, resultEvent, statusEvent, textEvent } from './events'
import {
    DEFAULT_FILE_CONTENT_MAX_BYTES,
    FilesystemError,
    listFilesystemDirectory,
    readFilesystemFile,
    statFilesystemEntry,
} from './filesystem'
import type { AdminParentMessage, AdminWorkerMessage, ResearchParentMessage, ResearchWorkerMessage } from './ipc'
import { HogbotLogWriter } from './log-writer'
import { PostHogApiClient } from './posthog-api'
import type { HogbotBusyState, HogbotNotificationEvent, HogbotScope, HogbotStatus } from './types'

export interface HogbotServerConfig {
    port: number
    teamId: number
    workspacePath: string
    publicBaseUrl: string
    sandboxConnectToken?: string
    posthogApiUrl: string
    posthogApiKey: string
    adminWorkerPath?: string
    researchWorkerPath?: string
    heartbeatIntervalMs?: number
    exitOnFatal?: boolean
    onFatal?: (error: Error) => void
    listen?: boolean
}

interface PendingAdminRequest {
    id: string
    resolve: (response: string) => void
    reject: (error: Error) => void
}

interface SseClient {
    scope: 'all' | HogbotScope
    signalId?: string
    send: (event: HogbotNotificationEvent) => void
    close: () => void
}

function randomId(): string {
    return randomBytes(16).toString('hex')
}

function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => {
        setTimeout(resolve, ms)
    })
}

function childEnv(config: HogbotServerConfig): NodeJS.ProcessEnv {
    return {
        ...process.env,
        HOGBOT_WORKSPACE_PATH: config.workspacePath,
    }
}

const DEFAULT_RESEARCH_README = [
    '# Hogbot Research',
    '',
    'This directory contains markdown files produced and maintained by Hogbot research runs.',
    '',
    'Expected usage:',
    '- Each signal can create or update a markdown file here.',
    '- Humans should review these files directly.',
    '- Keep the content concise, readable, and current.',
    '',
].join('\n')

export class HogbotServer {
    private readonly app = new Hono()
    private readonly apiClient: PostHogApiClient
    private readonly logWriter: HogbotLogWriter
    private readonly sseClients = new Set<SseClient>()
    private readonly workerEnv: NodeJS.ProcessEnv
    private adminChild: ChildProcess | null = null
    private adminReady = false
    private researchChild: ChildProcess | null = null
    private server: ServerType | null = null
    private activeSignalId: string | null = null
    private lastError: string | null = null
    private heartbeatTimer: NodeJS.Timeout | null = null
    private pendingAdminRequest: PendingAdminRequest | null = null
    private stopping = false

    constructor(private readonly config: HogbotServerConfig) {
        this.workerEnv = childEnv(config)
        this.apiClient = new PostHogApiClient({
            apiUrl: config.posthogApiUrl,
            apiKey: config.posthogApiKey,
            teamId: config.teamId,
        })
        this.logWriter = new HogbotLogWriter(
            this.apiClient,
            (error) => {
                this.fatalExit(error)
            },
            path.join(config.workspacePath, 'hogbox-server.log')
        )
        this.configureRoutes()
    }

    async start(): Promise<void> {
        await this.ensureResearchWorkspace()
        await this.startAdminWorker()
        await this.apiClient.registerServer({
            sandboxUrl: this.config.publicBaseUrl,
            sandboxConnectToken: this.config.sandboxConnectToken ?? null,
            status: 'running',
        })
        this.startHeartbeatLoop()
        if (this.config.listen !== false) {
            this.server = serve({
                fetch: this.app.fetch,
                port: this.config.port,
            })
        }
    }

    private async ensureResearchWorkspace(): Promise<void> {
        const researchDir = path.join(this.config.workspacePath, 'research')
        const readmePath = path.join(researchDir, 'README.md')
        await mkdir(researchDir, { recursive: true })
        try {
            await writeFile(readmePath, DEFAULT_RESEARCH_README, { encoding: 'utf-8', flag: 'wx' })
        } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== 'EEXIST') {
                throw error
            }
        }
    }

    async stop(): Promise<void> {
        this.stopping = true
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer)
            this.heartbeatTimer = null
        }
        this.closeAllSseClients()
        this.pendingAdminRequest?.reject(new Error('Hogbot server shutting down'))
        this.pendingAdminRequest = null
        await Promise.all([
            this.stopChild(this.adminChild, { type: 'shutdown' } satisfies AdminParentMessage),
            this.stopChild(this.researchChild, { type: 'shutdown' } satisfies ResearchParentMessage),
        ])
        this.adminChild = null
        this.researchChild = null
        await this.logWriter.flushAll()
        await this.apiClient.unregisterServer().catch(() => undefined)
        this.server?.close()
    }

    getListeningPort(): number | null {
        const address = this.server?.address() as AddressInfo | null | undefined
        if (!address || typeof address === 'string') {
            return null
        }
        return address.port
    }

    private configureRoutes(): void {
        this.app.get('/health', (c) => {
            const response = {
                status: this.adminReady ? 'ok' : 'starting',
                team_id: this.config.teamId,
                busy: this.getBusyState(),
                active_signal_id: this.activeSignalId,
                admin_ready: this.adminReady,
                research_running: this.isResearchBusy(),
            }
            return c.json(response, this.adminReady ? 200 : 503)
        })

        this.app.get('/logs', (c) => {
            const requestedScope = c.req.query('scope')
            const scope = requestedScope === 'admin' || requestedScope === 'research' ? requestedScope : 'all'
            const signalId = c.req.query('signal_id') ?? undefined
            c.header('X-Accel-Buffering', 'no')
            return streamSSE(c, async (stream) => {
                let clientRef: SseClient | null = null
                let closed = false
                let writeQueue = Promise.resolve()

                const closeClient = (): void => {
                    if (closed) {
                        return
                    }
                    closed = true
                    if (clientRef) {
                        this.sseClients.delete(clientRef)
                    }
                }

                clientRef = {
                    scope,
                    signalId,
                    send: (event) => {
                        writeQueue = writeQueue
                            .then(() => stream.writeSSE({ data: JSON.stringify(event) }))
                            .catch(() => {
                                closeClient()
                            })
                    },
                    close: closeClient,
                }
                this.sseClients.add(clientRef)

                const keepAlive = setInterval(() => {
                    writeQueue = writeQueue
                        .then(async () => {
                            await stream.write(': keepalive\n\n')
                        })
                        .catch(() => {
                            closeClient()
                        })
                }, 15000)

                const onAbort = (): void => {
                    clearInterval(keepAlive)
                    closeClient()
                }
                c.req.raw.signal.addEventListener('abort', onAbort, { once: true })

                try {
                    await new Promise<void>((resolve) => {
                        const poll = (): void => {
                            if (closed) {
                                resolve()
                                return
                            }
                            setTimeout(poll, 50)
                        }
                        poll()
                    })
                } finally {
                    clearInterval(keepAlive)
                    c.req.raw.signal.removeEventListener('abort', onAbort)
                    closeClient()
                }
            })
        })

        this.app.post('/send_message', async (c) => {
            if (!this.adminReady) {
                return c.json({ error: 'Admin worker is not ready' }, 503)
            }
            if (this.isAdminBusy()) {
                return c.json({ error: 'busy' }, 409)
            }

            const body = await c.req.json()
            if (!body || typeof body.content !== 'string' || body.content.trim() === '') {
                return c.json({ error: 'content is required' }, 400)
            }

            this.lastError = null
            void this.syncHeartbeat()

            try {
                const requestId = randomId()
                const response = await new Promise<string>((resolve, reject) => {
                    this.pendingAdminRequest = { id: requestId, resolve, reject }
                    this.adminChild?.send({
                        type: 'send_message',
                        requestId,
                        content: body.content,
                    } satisfies AdminParentMessage)
                }).finally(() => {
                    this.pendingAdminRequest = null
                    void this.syncHeartbeat()
                })

                return c.json({ response })
            } catch (error) {
                this.lastError = error instanceof Error ? error.message : String(error)
                if (this.lastError === 'Admin request cancelled') {
                    return c.json({ error: this.lastError }, 409)
                }
                return c.json({ error: this.lastError }, 500)
            }
        })

        this.app.post('/cancel', async (c) => {
            if (!this.isAdminBusy() || !this.pendingAdminRequest) {
                return c.json({ cancelled: false })
            }
            this.adminChild?.send({
                type: 'cancel',
                requestId: this.pendingAdminRequest.id,
            } satisfies AdminParentMessage)
            return c.json({ cancelled: true })
        })

        this.app.post('/research', async (c) => {
            if (!this.adminReady) {
                return c.json({ error: 'Admin worker is not ready' }, 503)
            }
            if (this.isResearchBusy()) {
                return c.json({ error: 'busy' }, 418)
            }

            const body = await c.req.json()
            if (!body || typeof body.signal_id !== 'string' || typeof body.prompt !== 'string') {
                return c.json({ error: 'signal_id and prompt are required' }, 400)
            }
            if (!body.signal_id.trim() || !body.prompt.trim()) {
                return c.json({ error: 'signal_id and prompt are required' }, 400)
            }

            await this.startResearchWorker(body.signal_id, body.prompt)
            return c.json({ status: 'started', signal_id: body.signal_id }, 202)
        })

        this.app.get('/filesystem/stat', async (c) => {
            try {
                return c.json(await statFilesystemEntry(this.config.workspacePath, c.req.query('path')))
            } catch (error) {
                return this.handleFilesystemError(error)
            }
        })

        this.app.get('/filesystem/list', async (c) => {
            try {
                return c.json(await listFilesystemDirectory(this.config.workspacePath, c.req.query('path')))
            } catch (error) {
                return this.handleFilesystemError(error)
            }
        })

        this.app.get('/filesystem/content', async (c) => {
            try {
                const maxBytesValue = c.req.query('max_bytes')
                const maxBytes = maxBytesValue ? Number(maxBytesValue) : DEFAULT_FILE_CONTENT_MAX_BYTES
                const encoding = c.req.query('encoding') === 'base64' ? 'base64' : 'utf-8'
                return c.json(
                    await readFilesystemFile(this.config.workspacePath, c.req.query('path'), encoding, maxBytes)
                )
            } catch (error) {
                return this.handleFilesystemError(error)
            }
        })
    }

    private handleFilesystemError(error: unknown): Response {
        if (error instanceof FilesystemError) {
            return new Response(JSON.stringify({ error: error.message }), {
                status: error.statusCode,
                headers: { 'Content-Type': 'application/json' },
            })
        }
        return new Response(JSON.stringify({ error: 'Filesystem request failed' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
        })
    }

    private async startAdminWorker(): Promise<void> {
        const workerPath = this.config.adminWorkerPath ?? path.resolve(__dirname, 'workers', 'admin-worker.js')
        const child = fork(workerPath, [], { env: this.workerEnv, stdio: ['inherit', 'inherit', 'inherit', 'ipc'] })
        this.adminChild = child

        await new Promise<void>((resolve, reject) => {
            let ready = false
            child.once('exit', (code: number | null) => {
                if (this.stopping) {
                    return
                }
                if (!ready) {
                    reject(new Error(`Admin worker exited before readiness with code ${code}`))
                    return
                }
                this.fatalExit(new Error(`Admin worker exited unexpectedly with code ${code}`))
            })
            child.once('error', (error: Error) => {
                if (!ready) {
                    reject(error)
                    return
                }
                this.fatalExit(error)
            })

            child.on('message', (message: AdminWorkerMessage) => {
                if (message.type === 'ready') {
                    this.adminReady = true
                    ready = true
                    resolve()
                    return
                }
                this.handleAdminWorkerMessage(message)
            })
        })
    }

    private async startResearchWorker(signalId: string, prompt: string): Promise<void> {
        const workerPath = this.config.researchWorkerPath ?? path.resolve(__dirname, 'workers', 'research-worker.js')
        const child = fork(workerPath, [], { env: this.workerEnv, stdio: ['inherit', 'inherit', 'inherit', 'ipc'] })
        this.researchChild = child
        this.activeSignalId = signalId
        this.lastError = null
        this.emitEvent(statusEvent('research', this.config.teamId, 'starting', { signalId }))
        await this.syncHeartbeat()

        await new Promise<void>((resolve, reject) => {
            let ready = false
            child.once('exit', (code: number | null) => {
                this.researchChild = null
                this.activeSignalId = null
                void this.syncHeartbeat()
                if (!ready && !this.stopping) {
                    reject(new Error(`Research worker exited before readiness with code ${code}`))
                    return
                }
                if (code === 0 || code === null) {
                    return
                }
                // The worker sends a failure event before exiting; exit code alone is not fatal.
            })

            child.on('message', (message: ResearchWorkerMessage) => {
                if (message.type === 'ready') {
                    ready = true
                    child.send({ type: 'start', signalId, prompt } satisfies ResearchParentMessage)
                    resolve()
                    return
                }
                this.handleResearchWorkerMessage(message, signalId)
            })

            child.once('error', (error: Error) => {
                reject(error)
            })
        })
    }

    private handleAdminWorkerMessage(message: AdminWorkerMessage): void {
        if (message.type === 'event') {
            this.emitWorkerEvent('admin', message)
            return
        }
        if (message.type === 'response') {
            this.pendingAdminRequest?.resolve(message.response)
            return
        }
        if (message.type === 'request_error') {
            this.pendingAdminRequest?.reject(new Error(message.error))
            return
        }
        if (message.type === 'cancelled') {
            this.pendingAdminRequest?.reject(new Error('Admin request cancelled'))
            return
        }
        if (message.type === 'fatal') {
            this.fatalExit(new Error(message.error))
        }
    }

    private handleResearchWorkerMessage(message: ResearchWorkerMessage, signalId: string): void {
        if (message.type === 'event') {
            this.emitWorkerEvent('research', message, signalId)
            return
        }
        if (message.type === 'done') {
            this.lastError = null
            return
        }
        if (message.type === 'failed') {
            this.lastError = message.error
            return
        }
        if (message.type === 'fatal') {
            this.lastError = message.error
            this.emitEvent(errorEvent('research', this.config.teamId, message.error, { signalId }))
            this.emitEvent(statusEvent('research', this.config.teamId, 'failed', { signalId, message: message.error }))
        }
    }

    private emitWorkerEvent(
        scope: HogbotScope,
        message: { method: string; params: Record<string, unknown> },
        signalId?: string
    ): void {
        const params = { ...message.params }
        const existingSignal = typeof params.signal_id === 'string' ? params.signal_id : signalId
        let event: HogbotNotificationEvent

        switch (message.method) {
            case '_hogbot/status':
                event = statusEvent(scope, this.config.teamId, String(params.status ?? 'running') as HogbotStatus, {
                    signalId: existingSignal,
                    message: typeof params.message === 'string' ? params.message : undefined,
                })
                break
            case '_hogbot/text':
                event = textEvent(scope, this.config.teamId, String(params.text ?? ''), {
                    signalId: existingSignal,
                    role: params.role === 'system' ? 'system' : 'assistant',
                })
                break
            case '_hogbot/result':
                event = resultEvent(scope, this.config.teamId, String(params.output ?? ''), {
                    signalId: existingSignal,
                })
                break
            case '_hogbot/error':
                event = errorEvent(scope, this.config.teamId, String(params.message ?? 'Unknown error'), {
                    signalId: existingSignal,
                })
                break
            default:
                event = consoleEvent(scope, this.config.teamId, 'info', String(params.message ?? ''), {
                    signalId: existingSignal,
                })
        }

        this.emitEvent(event, scope, existingSignal)
    }

    private emitEvent(event: HogbotNotificationEvent, scope?: HogbotScope, signalId?: string): void {
        for (const client of this.sseClients) {
            if (
                client.scope !== 'all' &&
                client.scope !== (scope ?? (String(event.notification.params.scope) as HogbotScope))
            ) {
                continue
            }
            if (
                client.signalId &&
                client.signalId !== signalId &&
                client.signalId !== String(event.notification.params.signal_id ?? '')
            ) {
                continue
            }
            client.send(event)
        }

        const resolvedScope = scope ?? (String(event.notification.params.scope) as HogbotScope)
        const resolvedSignalId =
            signalId ??
            (typeof event.notification.params.signal_id === 'string' ? event.notification.params.signal_id : undefined)
        this.logWriter.append(resolvedScope, event, resolvedSignalId)
    }

    private startHeartbeatLoop(): void {
        this.heartbeatTimer = setInterval(() => {
            void this.syncHeartbeat()
        }, this.config.heartbeatIntervalMs ?? 30000)
    }

    private isAdminBusy(): boolean {
        return this.pendingAdminRequest !== null
    }

    private isResearchBusy(): boolean {
        const child = this.researchChild
        return !!child && !child.killed && child.exitCode === null
    }

    private getBusyState(): HogbotBusyState {
        if (this.isResearchBusy()) {
            return 'research'
        }
        if (this.isAdminBusy()) {
            return 'admin'
        }
        return 'none'
    }

    private async syncHeartbeat(): Promise<void> {
        await this.apiClient.heartbeat({
            status: this.lastError ? 'error' : 'running',
            busy: this.getBusyState(),
            activeSignalId: this.activeSignalId,
            lastError: this.lastError,
        })
    }

    private closeAllSseClients(): void {
        for (const client of this.sseClients) {
            client.close()
        }
        this.sseClients.clear()
    }

    private safeSendToChild(child: ChildProcess | null, message: AdminParentMessage | ResearchParentMessage): void {
        if (!child) {
            return
        }
        if (child.killed || child.exitCode !== null || child.connected === false) {
            return
        }
        try {
            child.send(message, () => undefined)
        } catch {
            // Child may already have exited; shutdown is best-effort.
        }
    }

    private async stopChild(
        child: ChildProcess | null,
        message: AdminParentMessage | ResearchParentMessage
    ): Promise<void> {
        if (!child) {
            return
        }
        if (child.killed || child.exitCode !== null || child.connected === false) {
            return
        }

        const exitPromise = new Promise<void>((resolve) => {
            child.once('exit', () => resolve())
        })
        this.safeSendToChild(child, message)
        await Promise.race([exitPromise, sleep(2000)])
        if (child.exitCode !== null || child.killed) {
            return
        }

        child.kill('SIGTERM')
        await Promise.race([exitPromise, sleep(1000)])
        if (child.exitCode !== null || child.killed) {
            return
        }

        child.kill('SIGKILL')
        await Promise.race([exitPromise, sleep(1000)])
    }

    private fatalExit(error: Error): void {
        if (this.stopping) {
            return
        }
        this.lastError = error.message
        this.config.onFatal?.(error)
        void this.apiClient
            .heartbeat({
                status: 'error',
                busy: this.getBusyState(),
                activeSignalId: this.activeSignalId,
                lastError: error.message,
            })
            .catch(() => undefined)
            .finally(() => {
                if (this.config.exitOnFatal !== false) {
                    process.exit(1)
                }
            })
    }
}
