import { expect, test } from 'vitest'

import { getPostHogMcpServersFromEnv } from '../mcp'

test('builds PostHog MCP config from serialized environment JSON', () => {
    const servers = getPostHogMcpServersFromEnv({
        POSTHOG_MCP_SERVERS_JSON: JSON.stringify([
            {
                type: 'http',
                name: 'posthog',
                url: 'http://host.docker.internal:8787/mcp',
                headers: [
                    { name: 'Authorization', value: 'Bearer token-123' },
                    { name: 'x-posthog-project-id', value: '1' },
                ],
            },
        ]),
    })

    expect(servers.posthog.type).toBe('stdio')
    expect(servers.posthog.command).toBe(process.execPath)
    expect(servers.posthog.args.at(-1)).toContain('posthog-mcp-bridge')
    expect(servers.posthog.env?.HOGBOT_MCP_URL).toBe('http://host.docker.internal:8787/mcp')
    expect(JSON.parse(servers.posthog.env?.HOGBOT_MCP_HEADERS_JSON ?? '{}')).toEqual({
        Authorization: 'Bearer token-123',
        'x-posthog-project-id': '1',
    })
})

test('falls back to direct MCP environment variables', () => {
    const servers = getPostHogMcpServersFromEnv({
        POSTHOG_MCP_URL: 'https://mcp.posthog.com/mcp',
        POSTHOG_PERSONAL_API_KEY: 'token-456',
        POSTHOG_PROJECT_ID: '17',
    })

    expect(servers.posthog.type).toBe('stdio')
    expect(servers.posthog.command).toBe(process.execPath)
    expect(servers.posthog.args.at(-1)).toContain('posthog-mcp-bridge')
    expect(servers.posthog.env?.HOGBOT_MCP_URL).toBe('https://mcp.posthog.com/mcp')
    expect(JSON.parse(servers.posthog.env?.HOGBOT_MCP_HEADERS_JSON ?? '{}')).toEqual({
        Authorization: 'Bearer token-456',
        'x-posthog-mcp-version': '2',
        'x-posthog-project-id': '17',
        'x-posthog-read-only': 'false',
    })
})
