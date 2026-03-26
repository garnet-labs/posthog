import { execFile } from 'node:child_process'
import path from 'node:path'
import { promisify } from 'node:util'
import { afterEach, expect, test } from 'vitest'

import {
    createFakePostHogServer,
    createRuntimeDependencyRoot,
    createWorkspaceFixture,
    ensureServerDistBuilt,
    getAvailablePort,
    HOGBOT_PACKAGE_ROOT,
    POSTHOG_REPO_ROOT,
    signJwt,
    waitFor,
} from './helpers/runtime-fixtures'

const execFileAsync = promisify(execFile)
const dockerTest = process.env.HOGBOT_DOCKER_TESTS === '1' ? test : test.skip

const cleanups: Array<() => Promise<void>> = []

afterEach(async () => {
    while (cleanups.length > 0) {
        const cleanup = cleanups.pop()
        if (cleanup) {
            await cleanup()
        }
    }
})

async function docker(args: string[], env: NodeJS.ProcessEnv = {}): Promise<{ stdout: string; stderr: string }> {
    const result = await execFileAsync('docker', args, {
        env: {
            ...process.env,
            ...env,
        },
    })
    return {
        stdout: result.stdout,
        stderr: result.stderr,
    }
}

async function dockerImageExists(image: string): Promise<boolean> {
    try {
        await docker(['image', 'inspect', image])
        return true
    } catch {
        return false
    }
}

async function ensureBaseSandboxImage(): Promise<void> {
    if (await dockerImageExists('posthog-sandbox-base:latest')) {
        return
    }

    await docker([
        'build',
        '-f',
        path.join(POSTHOG_REPO_ROOT, 'products/tasks/backend/sandbox/images/Dockerfile.sandbox-base'),
        '-t',
        'posthog-sandbox-base',
        POSTHOG_REPO_ROOT,
    ])
}

async function buildHogbotDockerImage(): Promise<string> {
    const image = 'posthog-hogbot-local:test'
    await ensureBaseSandboxImage()
    await docker([
        'build',
        '-f',
        path.join(HOGBOT_PACKAGE_ROOT, 'server/images/Dockerfile.hogbot-local'),
        '-t',
        image,
        POSTHOG_REPO_ROOT,
    ])
    return image
}

dockerTest(
    'starts hogbot-server inside docker and serves admin, research, and filesystem endpoints',
    async () => {
        await ensureServerDistBuilt()
        const image = await buildHogbotDockerImage()
        const workspace = await createWorkspaceFixture()
        cleanups.push(workspace.cleanup)

        const deps = await createRuntimeDependencyRoot()
        cleanups.push(deps.cleanup)

        const api = await createFakePostHogServer()
        cleanups.push(api.close)

        const hostPort = await getAvailablePort()
        const containerName = `hogbot-test-${Date.now()}`
        cleanups.push(async () => {
            await docker(['rm', '-f', containerName]).catch(() => ({ stdout: '', stderr: '' }))
        })

        await docker(
            [
                'run',
                '-d',
                '--rm',
                '--name',
                containerName,
                '--add-host',
                'host.docker.internal:host-gateway',
                '-e',
                'POSTHOG_API_URL',
                '-e',
                'POSTHOG_PERSONAL_API_KEY',
                '-e',
                'NODE_OPTIONS',
                '-v',
                `${workspace.path}:/workspace`,
                '-v',
                `${deps.root}:/deps`,
                '-w',
                '/scripts',
                '-p',
                `${hostPort}:47821`,
                image,
                'node',
                '/scripts/node_modules/@posthog/products-hogbot/server/dist/bin.js',
                '--port',
                '47821',
                '--teamId',
                '1',
                '--workspacePath',
                '/workspace',
                '--publicBaseUrl',
                `http://host.docker.internal:${hostPort}`,
            ],
            {
                POSTHOG_API_URL: `http://host.docker.internal:${api.port}`,
                POSTHOG_PERSONAL_API_KEY: 'test-posthog-api-key',
                NODE_OPTIONS: '--require /deps/register-claude-sdk-mock.cjs',
            }
        )

        const baseUrl = `http://127.0.0.1:${hostPort}`
        try {
            await waitFor(async () => {
                try {
                    const response = await fetch(`${baseUrl}/health`)
                    return response.status === 200
                } catch {
                    return false
                }
            }, 20000)
        } catch {
            const logs = await docker(['logs', containerName]).catch(() => ({ stdout: '', stderr: '' }))
            throw new Error(`Container failed to become healthy.\nstdout:\n${logs.stdout}\nstderr:\n${logs.stderr}`)
        }

        const adminResponse = await fetch(`${baseUrl}/send_message`, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${signJwt()}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ content: 'hello-docker' }),
        })
        expect(adminResponse.status).toBe(200)
        expect(await adminResponse.json()).toEqual({ response: 'admin:hello-docker' })

        const researchResponse = await fetch(`${baseUrl}/research`, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${signJwt()}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ signal_id: 'sig-docker', prompt: 'slow-research' }),
        })
        expect(researchResponse.status).toBe(202)

        await waitFor(() =>
            Boolean(
                api.state.researchLogBatches['sig-docker']?.some((batch) =>
                    batch.some((event: any) => event.notification?.method === '_hogbot/result')
                )
            )
        )

        const researchFileResponse = await fetch(`${baseUrl}/filesystem/content?path=/research/sig-docker.md`, {
            headers: { Authorization: `Bearer ${signJwt()}` },
        })
        expect(researchFileResponse.status).toBe(200)
        expect((await researchFileResponse.json()).content).toContain('research:slow-research')

        const contentResponse = await fetch(`${baseUrl}/filesystem/content?path=/sample.txt`, {
            headers: { Authorization: `Bearer ${signJwt()}` },
        })
        expect(contentResponse.status).toBe(200)
        expect((await contentResponse.json()).content).toBe('workspace file')

        expect(api.state.registerCalls).toHaveLength(1)
        expect(api.state.adminLogBatches.length).toBeGreaterThan(0)
    },
    180000
)
