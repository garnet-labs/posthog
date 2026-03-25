import { afterEach, expect, test } from 'vitest'

import {
    createFakePostHogServer,
    createRuntimeDependencyRoot,
    createWorkspaceFixture,
    ensureServerDistBuilt,
    readSseUntilHttp,
    signJwt,
    startHogbotProcess,
    waitFor,
} from './helpers/runtime-fixtures'

const runtimeTest = process.env.HOGBOT_SOCKET_TESTS === '1' ? test : test.skip

const cleanups: Array<() => Promise<void>> = []

afterEach(async () => {
    while (cleanups.length > 0) {
        const cleanup = cleanups.pop()
        if (cleanup) {
            await cleanup()
        }
    }
})

runtimeTest(
    'launches the real server command and exercises admin, research, logs, cancel, and filesystem endpoints',
    async () => {
        await ensureServerDistBuilt()

        const workspace = await createWorkspaceFixture()
        cleanups.push(workspace.cleanup)

        const deps = await createRuntimeDependencyRoot()
        cleanups.push(deps.cleanup)

        const api = await createFakePostHogServer()
        cleanups.push(api.close)

        const server = await startHogbotProcess({
            workspacePath: workspace.path,
            posthogApiUrl: api.baseUrl,
            nodePath: deps.nodePath,
            mockRegisterPath: deps.registerPath,
        })
        cleanups.push(async () => {
            await server.stop()
        })

        const authHeaders = {
            Authorization: `Bearer ${signJwt()}`,
            'Content-Type': 'application/json',
        }

        const healthResponse = await fetch(`${server.baseUrl}/health`)
        expect(healthResponse.status).toBe(200)
        expect(await healthResponse.json()).toMatchObject({
            status: 'ok',
            team_id: 1,
            busy: 'none',
            admin_ready: true,
        })

        const adminResponse = await fetch(`${server.baseUrl}/send_message`, {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({ content: 'hello-runtime' }),
        })
        expect(adminResponse.status).toBe(200)
        expect(await adminResponse.json()).toEqual({ response: 'admin:hello-runtime' })

        const pendingAdminRequest = fetch(`${server.baseUrl}/send_message`, {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({ content: 'slow-admin' }),
        })

        await waitFor(async () => {
            const response = await fetch(`${server.baseUrl}/health`)
            const body = await response.json()
            return body.busy === 'admin'
        })

        const cancelResponse = await fetch(`${server.baseUrl}/cancel`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${signJwt()}` },
        })
        expect(cancelResponse.status).toBe(200)
        expect(await cancelResponse.json()).toEqual({ cancelled: true })

        const cancelledResponse = await pendingAdminRequest
        expect(cancelledResponse.status).toBe(409)
        expect(await cancelledResponse.json()).toEqual({ error: 'Admin request cancelled' })

        const researchEventsPromise = readSseUntilHttp(
            `${server.baseUrl}/logs?scope=research&signal_id=sig-runtime`,
            { Authorization: `Bearer ${signJwt()}` },
            (event) => event.notification?.method === '_hogbot/result'
        )
        await new Promise((resolve) => setTimeout(resolve, 100))

        const researchResponse = await fetch(`${server.baseUrl}/research`, {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({ signal_id: 'sig-runtime', prompt: 'slow-research' }),
        })
        expect(researchResponse.status).toBe(202)
        expect(await researchResponse.json()).toEqual({ status: 'started', signal_id: 'sig-runtime' })

        const busyAdminResponse = await fetch(`${server.baseUrl}/send_message`, {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({ content: 'blocked-during-research' }),
        })
        expect(busyAdminResponse.status).toBe(409)
        expect(await busyAdminResponse.json()).toEqual({ error: 'busy' })

        const researchEvents = await researchEventsPromise
        expect(researchEvents.some((event) => event.notification.method === '_hogbot/result')).toBe(true)

        await waitFor(() =>
            Boolean(
                api.state.researchLogBatches['sig-runtime']?.some((batch) =>
                    batch.some((event: any) => event.notification?.method === '_hogbot/result')
                )
            )
        )

        const failedResearchResponse = await fetch(`${server.baseUrl}/research`, {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({ signal_id: 'sig-failed', prompt: 'fail-research' }),
        })
        expect(failedResearchResponse.status).toBe(202)

        await waitFor(() =>
            Boolean(
                api.state.researchLogBatches['sig-failed']?.some((batch) =>
                    batch.some((event: any) => event.notification?.method === '_hogbot/status')
                )
            )
        )

        const postFailureAdminResponse = await fetch(`${server.baseUrl}/send_message`, {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({ content: 'after-research-recovery' }),
        })
        expect(postFailureAdminResponse.status).toBe(200)
        expect(await postFailureAdminResponse.json()).toEqual({ response: 'admin:after-research-recovery' })

        const statResponse = await fetch(`${server.baseUrl}/filesystem/stat?path=/sample.txt`, {
            headers: { Authorization: `Bearer ${signJwt()}` },
        })
        expect(statResponse.status).toBe(200)

        const contentResponse = await fetch(`${server.baseUrl}/filesystem/content?path=/sample.txt`, {
            headers: { Authorization: `Bearer ${signJwt()}` },
        })
        expect(contentResponse.status).toBe(200)
        expect((await contentResponse.json()).content).toBe('workspace file')

        await waitFor(() =>
            api.state.adminLogBatches.some((batch) =>
                batch.some((event: any) => event.notification?.method === '_hogbot/result')
            )
        )
        expect(api.state.registerCalls).toHaveLength(1)
        expect(api.state.heartbeatCalls.length).toBeGreaterThan(0)

        const exitCode = await server.stop()
        expect(exitCode).toBe(0)
        cleanups.pop()
        expect(api.state.unregisterCalls).toBe(1)
    },
    20000
)

runtimeTest(
    'exits the parent process when the real admin worker fatally fails',
    async () => {
        await ensureServerDistBuilt()

        const workspace = await createWorkspaceFixture()
        cleanups.push(workspace.cleanup)

        const deps = await createRuntimeDependencyRoot()
        cleanups.push(deps.cleanup)

        const api = await createFakePostHogServer()
        cleanups.push(api.close)

        const server = await startHogbotProcess({
            workspacePath: workspace.path,
            posthogApiUrl: api.baseUrl,
            nodePath: deps.nodePath,
            mockRegisterPath: deps.registerPath,
        })

        cleanups.push(async () => {
            if (server.child.exitCode === null) {
                await server.stop()
            }
        })

        const controller = new AbortController()
        const pendingRequest = fetch(`${server.baseUrl}/send_message`, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${signJwt()}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ content: 'fatal-admin' }),
            signal: controller.signal,
        }).catch(() => null)

        await waitFor(() => server.child.exitCode !== null, 5000)
        controller.abort()
        await pendingRequest

        expect(server.child.exitCode).not.toBe(0)
        expect(
            api.state.heartbeatCalls.some(
                (call: any) => call.status === 'error' && String(call.last_error ?? '').includes('mock admin fatal')
            )
        ).toBe(true)
    },
    20000
)
