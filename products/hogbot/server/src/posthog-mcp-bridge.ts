import process from 'process'
import { URL } from 'url'

type JsonRpcMessage = Record<string, unknown>

function log(message: string, error?: unknown): void {
    const suffix =
        error === undefined ? '' : ` ${error instanceof Error ? error.stack || error.message : String(error)}`
    process.stderr.write(`[hogbot-mcp-bridge] ${message}${suffix}\n`)
}

function getRequiredEnv(name: string): string {
    const value = process.env[name]
    if (!value) {
        throw new Error(`Missing required environment variable ${name}`)
    }
    return value
}

function parseHeaders(serialized: string): Record<string, string> {
    const parsed = JSON.parse(serialized) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('HOGBOT_MCP_HEADERS_JSON must be a JSON object')
    }

    return Object.fromEntries(
        Object.entries(parsed).filter((entry): entry is [string, string] => typeof entry[1] === 'string')
    )
}

function serializeMessage(message: JsonRpcMessage): string {
    return `${JSON.stringify(message)}\n`
}

function isObject(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isInitializedNotification(message: JsonRpcMessage): boolean {
    return message.jsonrpc === '2.0' && message.method === 'notifications/initialized'
}

class ReadBuffer {
    private buffer?: Buffer

    append(chunk: Buffer): void {
        this.buffer = this.buffer ? Buffer.concat([this.buffer, chunk]) : chunk
    }

    readMessage(): JsonRpcMessage | null {
        if (!this.buffer) {
            return null
        }

        const index = this.buffer.indexOf('\n')
        if (index === -1) {
            return null
        }

        const line = this.buffer.toString('utf8', 0, index).replace(/\r$/, '')
        this.buffer = this.buffer.subarray(index + 1)
        return JSON.parse(line) as JsonRpcMessage
    }
}

class SseParser {
    private buffer = ''
    private eventName = ''
    private dataLines: string[] = []
    private lastEventId = ''
    private retryMs?: number

    append(chunk: string): JsonRpcMessage[] {
        this.buffer += chunk
        const messages: JsonRpcMessage[] = []

        while (true) {
            const index = this.buffer.indexOf('\n')
            if (index === -1) {
                break
            }

            const line = this.buffer.slice(0, index).replace(/\r$/, '')
            this.buffer = this.buffer.slice(index + 1)

            if (line === '') {
                const data = this.dataLines.join('\n')
                if (data && (!this.eventName || this.eventName === 'message')) {
                    messages.push(JSON.parse(data) as JsonRpcMessage)
                }
                this.eventName = ''
                this.dataLines = []
                continue
            }

            if (line.startsWith(':')) {
                continue
            }

            const separatorIndex = line.indexOf(':')
            const field = separatorIndex === -1 ? line : line.slice(0, separatorIndex)
            const rawValue = separatorIndex === -1 ? '' : line.slice(separatorIndex + 1)
            const value = rawValue.startsWith(' ') ? rawValue.slice(1) : rawValue

            if (field === 'event') {
                this.eventName = value
            } else if (field === 'data') {
                this.dataLines.push(value)
            } else if (field === 'id') {
                this.lastEventId = value
            } else if (field === 'retry') {
                const retry = Number.parseInt(value, 10)
                if (Number.isFinite(retry)) {
                    this.retryMs = retry
                }
            }
        }

        return messages
    }

    getLastEventId(): string | undefined {
        return this.lastEventId || undefined
    }

    getRetryMs(): number | undefined {
        return this.retryMs
    }
}

class StreamableHttpMcpClient {
    private readonly headers: Record<string, string>
    private readonly url: URL
    private sessionId?: string
    private sseAbortController?: AbortController
    private reconnectTimer?: NodeJS.Timeout
    private lastEventId?: string
    private closing = false
    onmessage?: (message: JsonRpcMessage) => Promise<void> | void
    onerror?: (error: unknown) => void
    onclose?: () => void

    constructor(url: URL, headers: Record<string, string>) {
        this.url = url
        this.headers = headers
    }

    async start(): Promise<void> {}

    async send(message: JsonRpcMessage): Promise<void> {
        const headers = new Headers(this.headers)
        headers.set('content-type', 'application/json')
        headers.set('accept', 'application/json, text/event-stream')
        if (this.sessionId) {
            headers.set('mcp-session-id', this.sessionId)
        }

        const response = await fetch(this.url, {
            method: 'POST',
            headers,
            body: JSON.stringify(message),
        })

        const responseSessionId = response.headers.get('mcp-session-id')
        if (responseSessionId) {
            this.sessionId = responseSessionId
        }

        if (!response.ok) {
            const body = await response.text().catch(() => '')
            throw new Error(`POST ${this.url} failed with ${response.status}: ${body}`)
        }

        if (response.status === 202) {
            await response.body?.cancel()
            if (isInitializedNotification(message)) {
                await this.startSse()
            }
            return
        }

        const contentType = response.headers.get('content-type') ?? ''
        if (contentType.includes('application/json')) {
            const payload = (await response.json()) as unknown
            await this.deliverPayload(payload)
            return
        }

        if (contentType.includes('text/event-stream')) {
            await this.consumeSse(response.body)
            return
        }

        await response.body?.cancel()
        throw new Error(`Unexpected MCP content type: ${contentType}`)
    }

    async close(): Promise<void> {
        this.closing = true
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer)
            this.reconnectTimer = undefined
        }
        this.sseAbortController?.abort()
        this.onclose?.()
    }

    private async deliverPayload(payload: unknown): Promise<void> {
        const messages = Array.isArray(payload) ? payload : [payload]
        for (const message of messages) {
            if (isObject(message)) {
                await this.onmessage?.(message)
            }
        }
    }

    private async startSse(): Promise<void> {
        if (this.sseAbortController || this.closing) {
            return
        }

        const controller = new AbortController()
        this.sseAbortController = controller

        try {
            const headers = new Headers(this.headers)
            headers.set('accept', 'text/event-stream')
            if (this.sessionId) {
                headers.set('mcp-session-id', this.sessionId)
            }
            if (this.lastEventId) {
                headers.set('last-event-id', this.lastEventId)
            }

            const response = await fetch(this.url, {
                method: 'GET',
                headers,
                signal: controller.signal,
            })

            if (!response.ok) {
                const body = await response.text().catch(() => '')
                throw new Error(`GET ${this.url} failed with ${response.status}: ${body}`)
            }

            await this.consumeSse(response.body, true)
        } catch (error) {
            if (!this.closing) {
                this.onerror?.(error)
                this.scheduleReconnect()
            }
        } finally {
            if (this.sseAbortController === controller) {
                this.sseAbortController = undefined
            }
        }
    }

    private scheduleReconnect(): void {
        if (this.reconnectTimer || this.closing) {
            return
        }

        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = undefined
            void this.startSse()
        }, 1000)
    }

    private async consumeSse(body: ReadableStream<Uint8Array> | null, keepOpen = false): Promise<void> {
        if (!body) {
            return
        }

        const parser = new SseParser()
        const reader = body.getReader()
        const decoder = new TextDecoder()

        try {
            while (true) {
                const { done, value } = await reader.read()
                if (done) {
                    break
                }

                const messages = parser.append(decoder.decode(value, { stream: true }))
                const lastEventId = parser.getLastEventId()
                if (lastEventId) {
                    this.lastEventId = lastEventId
                }
                for (const message of messages) {
                    await this.onmessage?.(message)
                }
            }
        } finally {
            reader.releaseLock()
        }

        if (keepOpen && !this.closing) {
            const retryMs = parser.getRetryMs()
            if (retryMs && Number.isFinite(retryMs)) {
                this.reconnectTimer = setTimeout(() => {
                    this.reconnectTimer = undefined
                    void this.startSse()
                }, retryMs)
                return
            }
            this.scheduleReconnect()
        }
    }
}

async function main(): Promise<void> {
    const url = new URL(getRequiredEnv('HOGBOT_MCP_URL'))
    const headers = parseHeaders(process.env.HOGBOT_MCP_HEADERS_JSON ?? '{}')
    const input = new ReadBuffer()
    const remote = new StreamableHttpMcpClient(url, headers)
    let sendChain = Promise.resolve()

    let shuttingDown = false

    const shutdown = async (code: number): Promise<void> => {
        if (shuttingDown) {
            return
        }
        shuttingDown = true

        const closeQuietly = async (closeable: { close: () => Promise<void> }): Promise<void> => {
            try {
                await closeable.close()
            } catch {}
        }

        await closeQuietly(remote)
        process.exit(code)
    }

    const forwardToRemote = (message: JsonRpcMessage): void => {
        sendChain = sendChain
            .then(() => remote.send(message))
            .catch((error) => {
                log('Failed to forward stdio request to remote MCP server.', error)
                void shutdown(1)
            })
    }

    const forwardToStdio = async (message: JsonRpcMessage): Promise<void> => {
        await new Promise<void>((resolve, reject) => {
            const serialized = serializeMessage(message)
            if (process.stdout.write(serialized)) {
                resolve()
                return
            }
            process.stdout.once('drain', resolve)
            process.stdout.once('error', reject)
        })
    }

    remote.onmessage = forwardToStdio

    remote.onerror = (error: unknown) => {
        log('Remote MCP transport error.', error)
        void shutdown(1)
    }
    remote.onclose = () => {
        void shutdown(0)
    }

    process.stdin.on('data', (chunk: Buffer) => {
        input.append(chunk)

        while (true) {
            try {
                const message = input.readMessage()
                if (!message) {
                    break
                }
                if (!isObject(message)) {
                    continue
                }
                forwardToRemote(message)
            } catch (error) {
                log('Failed to parse stdio MCP message.', error)
                void shutdown(1)
                return
            }
        }
    })
    process.stdin.on('error', (error: unknown) => {
        log('Stdio transport error.', error)
        void shutdown(1)
    })
    process.stdin.on('close', () => {
        void shutdown(0)
    })

    process.on('SIGINT', () => {
        void shutdown(0)
    })
    process.on('SIGTERM', () => {
        void shutdown(0)
    })

    process.stdin.resume()
    await remote.start()
}

void main().catch((error) => {
    log('Bridge startup failed.', error)
    process.exit(1)
})
