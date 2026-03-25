import { mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import path from 'path'
import { afterEach, expect, test, vi } from 'vitest'

import { HogbotServer } from '../hogbot-server'

const FIXTURES_DIR = path.resolve(__dirname, 'fixtures')

async function waitFor(predicate: () => boolean | Promise<boolean>, timeoutMs = 3000): Promise<void> {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
        if (await predicate()) {
            return
        }
        await new Promise((resolve) => setTimeout(resolve, 25))
    }
    throw new Error('Timed out waiting for condition')
}

async function readSseUntil(response: Response, predicate: (event: any) => boolean, timeoutMs = 3000): Promise<any[]> {
    if (!response.body) {
        throw new Error('Response body is missing')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    const deadline = Date.now() + timeoutMs
    let buffer = ''
    const events: any[] = []

    while (Date.now() < deadline) {
        const result = await Promise.race([
            reader.read(),
            new Promise<{ done: true; value?: undefined }>((resolve) => setTimeout(() => resolve({ done: true }), 100)),
        ])

        if (result.value) {
            buffer += decoder.decode(result.value, { stream: true })
            const frames = buffer.split('\n\n')
            buffer = frames.pop() ?? ''
            for (const frame of frames) {
                const line = frame.split('\n').find((candidate) => candidate.startsWith('data: '))
                if (!line) {
                    continue
                }
                const event = JSON.parse(line.slice('data: '.length))
                events.push(event)
                if (predicate(event)) {
                    await reader.cancel()
                    return events
                }
            }
        }
    }

    await reader.cancel()
    throw new Error('Timed out waiting for SSE event')
}

interface FakeApiState {
    registerCalls: unknown[]
    heartbeatCalls: unknown[]
    unregisterCalls: number
    adminLogBatches: unknown[][]
    researchLogBatches: Record<string, unknown[][]>
}

async function readBody(init: RequestInit | undefined): Promise<unknown> {
    if (!init?.body) {
        return {}
    }
    if (typeof init.body === 'string') {
        return JSON.parse(init.body)
    }
    return JSON.parse(String(init.body))
}

interface IntegrationContext {
    request: (path: string, init?: RequestInit) => Promise<Response>
    apiState: FakeApiState
    server: HogbotServer
    cleanup: () => Promise<void>
}

async function startIntegrationContext(
    options: { onFatal?: (error: Error) => void } = {}
): Promise<IntegrationContext> {
    const workspacePath = mkdtempSync(path.join(tmpdir(), 'hogbot-workspace-'))
    writeFileSync(path.join(workspacePath, 'sample.txt'), 'workspace file')

    const apiState: FakeApiState = {
        registerCalls: [],
        heartbeatCalls: [],
        unregisterCalls: 0,
        adminLogBatches: [],
        researchLogBatches: {},
    }

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const pathname = new URL(url).pathname
        const body = await readBody(init)
        const prefix = '/api/projects/1/hogbot'

        if (pathname === `${prefix}/server/register/`) {
            apiState.registerCalls.push(body)
        } else if (pathname === `${prefix}/server/heartbeat/`) {
            apiState.heartbeatCalls.push(body)
        } else if (pathname === `${prefix}/server/unregister/`) {
            apiState.unregisterCalls += 1
        } else if (pathname === `${prefix}/admin/append_log/`) {
            apiState.adminLogBatches.push(((body as { entries?: unknown[] }).entries ?? []) as unknown[])
        } else {
            const researchMatch = pathname.match(new RegExp(`^${prefix}/research/([^/]+)/append_log/$`))
            if (researchMatch) {
                const signalId = decodeURIComponent(researchMatch[1])
                apiState.researchLogBatches[signalId] = apiState.researchLogBatches[signalId] ?? []
                apiState.researchLogBatches[signalId].push(
                    ((body as { entries?: unknown[] }).entries ?? []) as unknown[]
                )
            }
        }

        return new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
        })
    })

    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    const server = new HogbotServer({
        port: 0,
        teamId: 1,
        workspacePath,
        publicBaseUrl: 'http://hogbot.local',
        posthogApiUrl: 'http://posthog.test',
        posthogApiKey: 'test-api-key',
        adminWorkerPath: path.join(FIXTURES_DIR, 'fake-admin-worker.cjs'),
        researchWorkerPath: path.join(FIXTURES_DIR, 'fake-research-worker.cjs'),
        heartbeatIntervalMs: 50,
        exitOnFatal: false,
        onFatal: options.onFatal,
        listen: false,
    })

    await server.start()

    const app = (server as any).app as { request: (input: string, init?: RequestInit) => Promise<Response> }
    const request = (targetPath: string, init?: RequestInit): Promise<Response> =>
        app.request(`http://hogbot.local${targetPath}`, init)

    const cleanup = async (): Promise<void> => {
        await server.stop().catch(() => undefined)
        vi.unstubAllGlobals()
        rmSync(workspacePath, { recursive: true, force: true })
    }

    return {
        request,
        apiState,
        server,
        cleanup,
    }
}

const cleanups: Array<() => Promise<void>> = []

afterEach(async () => {
    while (cleanups.length > 0) {
        const cleanup = cleanups.pop()
        if (cleanup) {
            await cleanup()
        }
    }
})

test('returns admin responses and appends admin logs', async () => {
    const context = await startIntegrationContext()
    cleanups.push(context.cleanup)

    const response = await context.request('/send_message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: 'hello' }),
    })

    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ response: 'admin:hello' })

    await waitFor(() =>
        context.apiState.adminLogBatches.some((batch) =>
            batch.some((event: any) => event.notification?.method === '_hogbot/result')
        )
    )
    expect(context.apiState.registerCalls).toHaveLength(1)
    expect(context.apiState.heartbeatCalls.length).toBeGreaterThan(0)
})

test('accepts unauthenticated requests on protected endpoints', async () => {
    const context = await startIntegrationContext()
    cleanups.push(context.cleanup)

    const response = await context.request('/send_message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: 'hello' }),
    })

    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ response: 'admin:hello' })
})

test('cancels a slow admin request', async () => {
    const context = await startIntegrationContext()
    cleanups.push(context.cleanup)

    const pendingResponse = context.request('/send_message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: 'slow-admin' }),
    })

    await waitFor(async () => {
        const health = await context.request('/health')
        const body = await health.json()
        return body.busy === 'admin'
    })

    const cancelResponse = await context.request('/cancel', {
        method: 'POST',
    })
    expect(cancelResponse.status).toBe(200)
    expect(await cancelResponse.json()).toEqual({ cancelled: true })

    const response = await pendingResponse
    expect(response.status).toBe(409)
    expect(await response.json()).toEqual({ error: 'Admin request cancelled' })
})

test('runs research jobs, streams sse events, and rejects concurrent work', async () => {
    const context = await startIntegrationContext()
    cleanups.push(context.cleanup)

    const sseResponse = await context.request('/logs?scope=research&signal_id=sig-1')
    expect(sseResponse.status).toBe(200)

    const researchResponse = await context.request('/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signal_id: 'sig-1', prompt: 'slow-research' }),
    })
    expect(researchResponse.status).toBe(202)

    const conflictResponse = await context.request('/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signal_id: 'sig-2', prompt: 'second' }),
    })
    expect(conflictResponse.status).toBe(409)

    const events = await readSseUntil(sseResponse, (event) => event.notification?.method === '_hogbot/result', 4000)
    expect(events.some((event) => event.notification.method === '_hogbot/result')).toBe(true)

    await waitFor(() => Boolean(context.apiState.researchLogBatches['sig-1']?.length))
    await waitFor(async () => {
        const health = await context.request('/health')
        const body = await health.json()
        return body.busy === 'none'
    })

    const adminResponse = await context.request('/send_message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: 'after-research' }),
    })
    expect(adminResponse.status).toBe(200)
})

test('keeps the server alive when research worker fails', async () => {
    const onFatal = vi.fn()
    const context = await startIntegrationContext({ onFatal })
    cleanups.push(context.cleanup)

    const response = await context.request('/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signal_id: 'sig-fail', prompt: 'fail-research' }),
    })
    expect(response.status).toBe(202)

    await waitFor(async () => {
        const health = await context.request('/health')
        const body = await health.json()
        return body.busy === 'none'
    })

    const adminResponse = await context.request('/send_message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: 'still-alive' }),
    })
    expect(adminResponse.status).toBe(200)
    expect(onFatal).not.toHaveBeenCalled()
})

test('serves filesystem endpoints relative to the workspace root', async () => {
    const context = await startIntegrationContext()
    cleanups.push(context.cleanup)

    const statResponse = await context.request('/filesystem/stat?path=/sample.txt')
    expect(statResponse.status).toBe(200)

    const contentResponse = await context.request('/filesystem/content?path=/sample.txt')
    expect(contentResponse.status).toBe(200)
    expect((await contentResponse.json()).content).toBe('workspace file')

    const traversalResponse = await context.request('/filesystem/stat?path=/../secret')
    expect(traversalResponse.status).toBe(400)
})

test('reports a fatal error when the admin worker exits unexpectedly', async () => {
    const onFatal = vi.fn()
    const context = await startIntegrationContext({ onFatal })
    cleanups.push(context.cleanup)

    const adminChild = (context.server as any).adminChild as { kill: (signal?: string) => void }
    adminChild.kill('SIGKILL')

    await waitFor(() => onFatal.mock.calls.length > 0)
    expect(onFatal.mock.calls[0][0].message).toContain('Admin worker exited unexpectedly')
})
