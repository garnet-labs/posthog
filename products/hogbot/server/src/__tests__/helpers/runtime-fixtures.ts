import { execFile, spawn, type ChildProcess } from 'node:child_process'
import { createSign } from 'node:crypto'
import { once } from 'node:events'
import { cp, mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { createServer, request as httpRequest, type IncomingMessage, type ServerResponse } from 'node:http'
import { createServer as createNetServer } from 'node:net'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)

const TEST_RSA_PRIVATE_KEY = `-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDqh94SYMFsvG4C
Co9BSGjtPr2/OxzuNGr41O4+AMkDQRd9pKO49DhTA4VzwnOvrH8y4eI9N8OQne7B
wpdoouSn4DoDAS/b3SUfij/RoFUSyZiTQoWz0H6o2Vuufiz0Hf+BzlZEVnhSQ1ru
vqSf+4l8cWgeMXaFXgdD5kQ8GjvR5uqKxvO2Env1hMJRKeOOEGgCep/0c6SkMUTX
SeC+VjypVg9+8yPxtIpOQ7XKv+7e/PA0ilqehRQh4fo9BAWjUW1+HnbtsjJAjjfv
ngzIjpajuQVyMi7G79v8OvijhLMJjJBh3TdbVIfi+RkVj/H94UUfKWRfJA0eLykA
VvTiFf0nAgMBAAECggEABkLBQWFW2IXBNAm/IEGEF408uH2l/I/mqSTaBUq1EwKq
U17RRg8y77hg2CHBP9fNf3i7NuIltNcaeA6vRwpOK1MXiVv/QJHLO2fP41Mx4jIC
gi/c7NtsfiprQaG5pnykhP0SnXlndd65bzUkpOasmWdXnbK5VL8ZV40uliInJafE
1Eo9qSYCJxHmivU/4AbiBgygOAo1QIiuuUHcx0YGknLrBaMQETuvWJGE3lxVQ30/
EuRyA3r6BwN2T0z47PZBzvCpg/C1KeoYuKSMwMyEXfl+a8NclqdROkVaenmZpvVH
0lAvFDuPrBSDmU4XJbKCEfwfHjRkiWAFaTrKntGQtQKBgQD/ILoK4U9DkJoKTYvY
9lX7dg6wNO8jGLHNufU8tHhU+QnBMH3hBXrAtIKQ1sGs+D5rq/O7o0Balmct9vwb
CQZ1EpPfa83Thsv6Skd7lWK0JF7g2vVk8kT4nY/eqkgZUWgkfdMp+OMg2drYiIE8
u+sRPTCdq4Tv5miRg0OToX2H/QKBgQDrVR2GXm6ZUyFbCy8A0kttXP1YyXqDVq7p
L4kqyUq43hmbjzIRM4YDN3EvgZvVf6eub6L/3HfKvWD/OvEhHovTvHb9jkwZ3FO+
YQllB/ccAWJs/Dw5jLAsX9O+eIe4lfwROib3vYLnDTAmrXD5VL35R5F0MsdRoxk5
lTCq1sYI8wKBgGA9ZjDIgXAJUjJkwkZb1l9/T1clALiKjjf+2AXIRkQ3lXhs5G9H
8+BRt5cPjAvFsTZIrS6xDIufhNiP/NXt96OeGG4FaqVKihOmhYSW+57cwXWs4zjr
Mx1dwnHKZlw2m0R4unlwy60OwUFBbQ8ODER6gqZXl1Qv5G5Px+Qe3Q25AoGAUl+s
wgfz9r9egZvcjBEQTeuq0pVTyP1ipET7YnqrKSK1G/p3sAW09xNFDzfy8DyK2UhC
agUl+VVoym47UTh8AVWK4R4aDUNOHOmifDbZjHf/l96CxjI0yJOSbq2J9FarsOwG
D9nKJE49eIxlayD6jnM6us27bxwEDF/odSRQlXkCgYEAxn9l/5kewWkeEA0Afe1c
Uf+mepHBLw1Pbg5GJYIZPC6e5+wRNvtFjM5J6h5LVhyb7AjKeLBTeohoBKEfUyUO
rl/ql9qDIh5lJFn3uNh7+r7tmG21Zl2pyh+O8GljjZ25mYhdiwl0uqzVZaINe2Wa
vbMnD1ZQKgL8LHgb02cbTsc=
-----END PRIVATE KEY-----`

export const HOGBOT_PACKAGE_ROOT = path.resolve(__dirname, '../../../../')
export const POSTHOG_REPO_ROOT = path.resolve(HOGBOT_PACKAGE_ROOT, '../..')
const CODE_NODE_MODULES = path.resolve(POSTHOG_REPO_ROOT, '../code/node_modules')
const TSUP_CLI = path.join(CODE_NODE_MODULES, 'tsup/dist/cli-default.js')
const DIST_BIN_PATH = path.join(HOGBOT_PACKAGE_ROOT, 'server/dist/bin.js')
const FIXTURES_DIR = path.resolve(__dirname, '../fixtures')

let buildPromise: Promise<void> | null = null

export interface FakeApiState {
    registerCalls: unknown[]
    heartbeatCalls: unknown[]
    unregisterCalls: number
    adminLogBatches: unknown[][]
    researchLogBatches: Record<string, unknown[][]>
}

export interface FakePostHogServer {
    baseUrl: string
    port: number
    state: FakeApiState
    close: () => Promise<void>
}

export interface RuntimeDependencyRoot {
    root: string
    nodePath: string
    registerPath: string
    cleanup: () => Promise<void>
}

export interface WorkspaceFixture {
    path: string
    cleanup: () => Promise<void>
}

export interface LaunchedHogbot {
    child: ChildProcess
    baseUrl: string
    stdout: string
    stderr: string
    stop: () => Promise<number | null>
}

function encodeBase64Url(value: string): string {
    return Buffer.from(value).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

export function signJwt(teamId = 1): string {
    const header = encodeBase64Url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
    const payload = encodeBase64Url(
        JSON.stringify({
            team_id: teamId,
            user_id: 2,
            distinct_id: 'hogbot-test-user',
            scope: 'hogbot',
            aud: 'posthog:sandbox_connection',
            exp: Math.floor(Date.now() / 1000) + 3600,
        })
    )
    const signer = createSign('RSA-SHA256')
    signer.update(`${header}.${payload}`)
    signer.end()
    const signature = signer
        .sign(TEST_RSA_PRIVATE_KEY, 'base64')
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/g, '')
    return `${header}.${payload}.${signature}`
}

export function getJwtPublicKey(): string {
    return TEST_RSA_PRIVATE_KEY
}

export async function waitFor(predicate: () => boolean | Promise<boolean>, timeoutMs = 10000): Promise<void> {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
        if (await predicate()) {
            return
        }
        await new Promise((resolve) => setTimeout(resolve, 25))
    }
    throw new Error('Timed out waiting for condition')
}

export async function readSseUntil(
    response: Response,
    predicate: (event: any) => boolean,
    timeoutMs = 5000
): Promise<any[]> {
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
            new Promise<{ done: true; value?: undefined }>((resolve) => {
                setTimeout(() => resolve({ done: true }), 100)
            }),
        ])

        if (!result.value) {
            continue
        }

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

    await reader.cancel()
    throw new Error('Timed out waiting for SSE event')
}

export async function readSseUntilHttp(
    url: string,
    headers: Record<string, string>,
    predicate: (event: any) => boolean,
    timeoutMs = 5000
): Promise<any[]> {
    return await new Promise<any[]>((resolve, reject) => {
        const events: any[] = []
        let buffer = ''
        let settled = false
        const target = new URL(url)

        const fail = (error: Error): void => {
            if (settled) {
                return
            }
            settled = true
            clearTimeout(timeout)
            reject(error)
        }

        const succeed = (value: any[]): void => {
            if (settled) {
                return
            }
            settled = true
            clearTimeout(timeout)
            resolve(value)
        }

        const request = httpRequest(
            {
                host: target.hostname,
                port: Number(target.port),
                path: `${target.pathname}${target.search}`,
                method: 'GET',
                headers,
            },
            (response) => {
                if (response.statusCode !== 200) {
                    fail(new Error(`Unexpected SSE status ${response.statusCode}`))
                    return
                }

                response.setEncoding('utf8')
                response.on('data', (chunk) => {
                    buffer += chunk
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
                            request.destroy()
                            response.destroy()
                            succeed(events)
                            return
                        }
                    }
                })
                response.on('error', (error) => fail(error instanceof Error ? error : new Error(String(error))))
                response.on('end', () => {
                    fail(new Error('SSE connection ended before the expected event arrived'))
                })
            }
        )

        request.on('error', (error) => fail(error instanceof Error ? error : new Error(String(error))))
        request.end()

        const timeout = setTimeout(() => {
            request.destroy()
            fail(new Error('Timed out waiting for SSE event'))
        }, timeoutMs)
    })
}

export async function getAvailablePort(): Promise<number> {
    const server = createNetServer()
    server.listen(0, '127.0.0.1')
    await once(server, 'listening')
    const address = server.address()
    if (!address || typeof address === 'string') {
        server.close()
        throw new Error('Failed to allocate a local port')
    }
    const port = address.port
    server.close()
    await once(server, 'close')
    return port
}

export async function ensureServerDistBuilt(): Promise<void> {
    if (!buildPromise) {
        buildPromise = execFileAsync(process.execPath, [TSUP_CLI, '--config', 'server/tsup.config.ts'], {
            cwd: HOGBOT_PACKAGE_ROOT,
            env: {
                ...process.env,
                NODE_PATH: CODE_NODE_MODULES,
            },
        }).then(() => undefined)
    }
    await buildPromise
}

export async function createWorkspaceFixture(): Promise<WorkspaceFixture> {
    const workspacePath = await mkdtemp(path.join(tmpdir(), 'hogbot-runtime-workspace-'))
    await writeFile(path.join(workspacePath, 'sample.txt'), 'workspace file')
    return {
        path: workspacePath,
        cleanup: async () => {
            await rm(workspacePath, { recursive: true, force: true })
        },
    }
}

async function writeMockClaudeSdk(targetDir: string): Promise<void> {
    const packageDir = path.join(targetDir, '@anthropic-ai', 'claude-agent-sdk')
    await mkdir(packageDir, { recursive: true })
    await writeFile(
        path.join(packageDir, 'package.json'),
        JSON.stringify(
            {
                name: '@anthropic-ai/claude-agent-sdk',
                version: '0.0.0-test',
                main: './index.cjs',
                exports: {
                    '.': {
                        require: './index.cjs',
                        import: './index.mjs',
                        default: './index.cjs',
                    },
                },
            },
            null,
            2
        )
    )
    await writeFile(
        path.join(packageDir, 'index.cjs'),
        await readFile(path.join(FIXTURES_DIR, 'mock-claude-agent-sdk.cjs'), 'utf-8')
    )
    await writeFile(
        path.join(packageDir, 'index.mjs'),
        await readFile(path.join(FIXTURES_DIR, 'mock-claude-agent-sdk.mjs'), 'utf-8')
    )
}

export async function createRuntimeDependencyRoot(): Promise<RuntimeDependencyRoot> {
    const root = await mkdtemp(path.join(tmpdir(), 'hogbot-runtime-deps-'))
    const nodeModulesDir = path.join(root, 'node_modules')
    const registerPath = path.join(root, 'register-claude-sdk-mock.cjs')
    await mkdir(path.join(nodeModulesDir, '@hono'), { recursive: true })
    await cp(path.join(CODE_NODE_MODULES, 'hono'), path.join(nodeModulesDir, 'hono'), { recursive: true })
    await cp(path.join(CODE_NODE_MODULES, '@hono', 'node-server'), path.join(nodeModulesDir, '@hono', 'node-server'), {
        recursive: true,
    })
    await writeMockClaudeSdk(nodeModulesDir)
    await writeFile(
        registerPath,
        [
            'const Module = require("module");',
            'const path = require("path");',
            'const originalLoad = Module._load;',
            'const mockPath = path.join(__dirname, "node_modules", "@anthropic-ai", "claude-agent-sdk", "index.cjs");',
            'Module._load = function patchedLoad(request, parent, isMain) {',
            '    if (request === "@anthropic-ai/claude-agent-sdk") {',
            '        return originalLoad(mockPath, parent, isMain);',
            '    }',
            '    return originalLoad(request, parent, isMain);',
            '};',
            '',
        ].join('\n')
    )

    return {
        root,
        nodePath: nodeModulesDir,
        registerPath,
        cleanup: async () => {
            await rm(root, { recursive: true, force: true })
        },
    }
}

async function readRequestJson(request: IncomingMessage): Promise<unknown> {
    const chunks: Buffer[] = []
    for await (const chunk of request) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
    }
    const body = Buffer.concat(chunks).toString('utf-8')
    if (!body) {
        return {}
    }
    return JSON.parse(body)
}

function writeJson(response: ServerResponse, statusCode: number, payload: unknown): void {
    response.writeHead(statusCode, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify(payload))
}

export async function createFakePostHogServer(): Promise<FakePostHogServer> {
    const port = await getAvailablePort()
    const state: FakeApiState = {
        registerCalls: [],
        heartbeatCalls: [],
        unregisterCalls: 0,
        adminLogBatches: [],
        researchLogBatches: {},
    }

    const server = createServer(async (request, response) => {
        const url = new URL(request.url ?? '/', `http://127.0.0.1:${port}`)
        const prefix = '/api/projects/1/hogbot'
        const pathName = url.pathname
        const body = request.method === 'GET' ? {} : await readRequestJson(request)

        if (pathName === `${prefix}/server/register/`) {
            state.registerCalls.push(body)
            writeJson(response, 200, { ok: true })
            return
        }

        if (pathName === `${prefix}/server/heartbeat/`) {
            state.heartbeatCalls.push(body)
            writeJson(response, 200, { ok: true })
            return
        }

        if (pathName === `${prefix}/server/unregister/`) {
            state.unregisterCalls += 1
            writeJson(response, 200, { ok: true })
            return
        }

        if (pathName === `${prefix}/admin/append_log/`) {
            const entries = ((body as { entries?: unknown[] }).entries ?? []) as unknown[]
            state.adminLogBatches.push(entries)
            writeJson(response, 200, { ok: true })
            return
        }

        const researchMatch = pathName.match(new RegExp(`^${prefix}/research/([^/]+)/append_log/$`))
        if (researchMatch) {
            const signalId = decodeURIComponent(researchMatch[1])
            const entries = ((body as { entries?: unknown[] }).entries ?? []) as unknown[]
            state.researchLogBatches[signalId] = state.researchLogBatches[signalId] ?? []
            state.researchLogBatches[signalId].push(entries)
            writeJson(response, 200, { ok: true })
            return
        }

        writeJson(response, 404, { error: `Unknown path: ${pathName}` })
    })

    server.listen(port, '127.0.0.1')
    await once(server, 'listening')

    return {
        baseUrl: `http://127.0.0.1:${port}`,
        port,
        state,
        close: async () => {
            server.close()
            await once(server, 'close')
        },
    }
}

export async function startHogbotProcess(options: {
    port?: number
    workspacePath: string
    posthogApiUrl: string
    nodePath: string
    mockRegisterPath?: string
    extraEnv?: NodeJS.ProcessEnv
}): Promise<LaunchedHogbot> {
    const port = options.port ?? (await getAvailablePort())
    let stdout = ''
    let stderr = ''
    const child = spawn(
        process.execPath,
        [
            DIST_BIN_PATH,
            '--port',
            String(port),
            '--teamId',
            '1',
            '--workspacePath',
            options.workspacePath,
            '--publicBaseUrl',
            `http://127.0.0.1:${port}`,
        ],
        {
            cwd: HOGBOT_PACKAGE_ROOT,
            env: {
                ...process.env,
                ...options.extraEnv,
                POSTHOG_API_URL: options.posthogApiUrl,
                POSTHOG_PERSONAL_API_KEY: 'test-posthog-api-key',
                NODE_PATH: options.nodePath,
                NODE_OPTIONS: [
                    process.env.NODE_OPTIONS,
                    options.mockRegisterPath ? `--require ${options.mockRegisterPath}` : '',
                ]
                    .filter(Boolean)
                    .join(' '),
            },
            stdio: ['ignore', 'pipe', 'pipe'],
        }
    )

    child.stdout?.on('data', (chunk: Buffer | string) => {
        stdout += chunk.toString()
    })
    child.stderr?.on('data', (chunk: Buffer | string) => {
        stderr += chunk.toString()
    })

    await waitFor(async () => {
        try {
            const response = await fetch(`http://127.0.0.1:${port}/health`)
            return response.status === 200
        } catch {
            if (child.exitCode !== null) {
                throw new Error(
                    `hogbot-server exited before it became healthy.\nstdout:\n${stdout}\nstderr:\n${stderr}`
                )
            }
            return false
        }
    })

    return {
        child,
        baseUrl: `http://127.0.0.1:${port}`,
        get stdout() {
            return stdout
        },
        get stderr() {
            return stderr
        },
        stop: async () => {
            if (child.exitCode !== null) {
                return child.exitCode
            }
            child.kill('SIGTERM')
            const result = await Promise.race([
                once(child, 'exit').then(([code]) => code as number | null),
                new Promise<number | null>((resolve) => {
                    setTimeout(() => resolve(null), 4000)
                }),
            ])
            if (result !== null) {
                return result
            }
            child.kill('SIGKILL')
            const [code] = (await once(child, 'exit')) as [number | null]
            return code
        },
    }
}
