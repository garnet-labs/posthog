import { describe, expect, it } from 'vitest'

import { SessionManager } from '@/lib/SessionManager'
import { registerToolSearchMode } from '@/tools/toolSearchMode'
import type { Context } from '@/tools/types'

function createMockContext(scopes: string[] = ['*']): Context {
    return {
        api: {} as any,
        cache: {} as any,
        env: {
            INKEEP_API_KEY: undefined,
            MCP_APPS_BASE_URL: undefined,
            POSTHOG_ANALYTICS_API_KEY: undefined,
            POSTHOG_ANALYTICS_HOST: undefined,
            POSTHOG_API_BASE_URL: undefined,
            POSTHOG_MCP_APPS_ANALYTICS_BASE_URL: undefined,
            POSTHOG_UI_APPS_TOKEN: undefined,
        },
        stateManager: {
            getApiKey: async () => ({ scopes }),
            getAiConsentGiven: async () => true,
        } as any,
        sessionManager: new SessionManager({} as any),
    }
}

// Collects tools registered on a mock McpServer
function createMockServer(): { server: any; registeredTools: Map<string, { config: any; handler: Function }> } {
    const registeredTools = new Map<string, { config: any; handler: Function }>()
    const server = {
        registerTool: (name: string, config: any, handler: Function) => {
            registeredTools.set(name, { config, handler })
        },
    }
    return { server, registeredTools }
}

describe('Tool Search Mode', () => {
    it('registers exactly 3 meta-tools', async () => {
        const { server, registeredTools } = createMockServer()
        const context = createMockContext()

        await registerToolSearchMode(server, context, {})

        expect(registeredTools.size).toBe(3)
        expect(registeredTools.has('tool_search')).toBe(true)
        expect(registeredTools.has('tool_schema')).toBe(true)
        expect(registeredTools.has('tool_call')).toBe(true)
    })

    describe('tool_search', () => {
        it('returns relevant results for a query', async () => {
            const { server, registeredTools } = createMockServer()
            const context = createMockContext()
            await registerToolSearchMode(server, context, {})

            const handler = registeredTools.get('tool_search')!.handler
            const result = await handler({ query: 'experiment', limit: 10 })

            const text = result.content[0].text
            expect(text).toContain('experiment')
        })

        it('returns results matching feature flag queries', async () => {
            const { server, registeredTools } = createMockServer()
            const context = createMockContext()
            await registerToolSearchMode(server, context, {})

            const handler = registeredTools.get('tool_search')!.handler
            const result = await handler({ query: 'feature flag', limit: 10 })

            const text = result.content[0].text
            expect(text).toContain('feature-flag')
        })

        it('respects limit parameter', async () => {
            const { server, registeredTools } = createMockServer()
            const context = createMockContext()
            await registerToolSearchMode(server, context, {})

            const handler = registeredTools.get('tool_search')!.handler
            const result = await handler({ query: 'get', limit: 2 })

            // The response is TOON-formatted, but should contain at most 2 results
            const text = result.content[0].text
            // Count occurrences of "name:" in the output (each result has a name field)
            const nameMatches = text.match(/"?name"?\s*[:=]/g) || []
            expect(nameMatches.length).toBeLessThanOrEqual(2)
        })

        it('respects feature filtering', async () => {
            const { server, registeredTools } = createMockServer()
            const context = createMockContext()
            await registerToolSearchMode(server, context, { features: ['flags'] })

            const handler = registeredTools.get('tool_search')!.handler
            const result = await handler({ query: 'dashboard', limit: 10 })

            // Dashboard tools should not appear when only flags feature is enabled
            const text = result.content[0].text
            expect(text).not.toContain('dashboard')
        })
    })

    describe('tool_schema', () => {
        it('returns JSON Schema for a valid tool', async () => {
            const { server, registeredTools } = createMockServer()
            const context = createMockContext()
            await registerToolSearchMode(server, context, {})

            const handler = registeredTools.get('tool_schema')!.handler
            const result = await handler({ tool_name: 'dashboard-get' })

            const text = result.content[0].text
            expect(text).toContain('dashboard-get')
            expect(text).toContain('inputSchema')
            expect(result.isError).toBeUndefined()
        })

        it('returns error for unknown tool', async () => {
            const { server, registeredTools } = createMockServer()
            const context = createMockContext()
            await registerToolSearchMode(server, context, {})

            const handler = registeredTools.get('tool_schema')!.handler
            const result = await handler({ tool_name: 'nonexistent-tool' })

            expect(result.isError).toBe(true)
            expect(result.content[0].text).toContain('not found')
        })

        it('returns error for tool outside allowed features', async () => {
            const { server, registeredTools } = createMockServer()
            const context = createMockContext()
            await registerToolSearchMode(server, context, { features: ['flags'] })

            const handler = registeredTools.get('tool_schema')!.handler
            const result = await handler({ tool_name: 'dashboard-get' })

            expect(result.isError).toBe(true)
            expect(result.content[0].text).toContain('not found')
        })
    })

    describe('tool_call', () => {
        it('returns error for unknown tool', async () => {
            const { server, registeredTools } = createMockServer()
            const context = createMockContext()
            await registerToolSearchMode(server, context, {})

            const handler = registeredTools.get('tool_call')!.handler
            const result = await handler({ tool_name: 'nonexistent-tool', params: {} })

            expect(result.isError).toBe(true)
            expect(result.content[0].text).toContain('not found')
        })

        it('returns validation error for invalid params', async () => {
            const { server, registeredTools } = createMockServer()
            const context = createMockContext()
            await registerToolSearchMode(server, context, {})

            const handler = registeredTools.get('tool_call')!.handler
            // entity-search requires a query param with minLength 1
            const result = await handler({ tool_name: 'entity-search', params: {} })

            expect(result.isError).toBe(true)
            expect(result.content[0].text).toContain('Invalid parameters')
        })

        it('returns error for tool outside allowed scopes', async () => {
            const { server, registeredTools } = createMockServer()
            // Only dashboard scopes — no experiment scopes
            const context = createMockContext(['dashboard:read'])
            await registerToolSearchMode(server, context, {})

            const handler = registeredTools.get('tool_call')!.handler
            const result = await handler({ tool_name: 'experiment-get-all', params: {} })

            expect(result.isError).toBe(true)
            expect(result.content[0].text).toContain('not found')
        })
    })
})
