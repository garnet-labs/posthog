type StdioMcpServerConfig = {
    type: 'stdio'
    command: string
    args: string[]
    env?: Record<string, string>
}

interface SerializedRemoteMcpServer {
    type: 'http' | 'sse'
    name: string
    url: string
    headers?: Array<{ name: string; value: string }>
}

function getBridgeEntrypoint(): string {
    try {
        return require.resolve('./posthog-mcp-bridge')
    } catch {
        return './posthog-mcp-bridge'
    }
}

function buildBridgeConfig(url: string, headers?: Record<string, string>): StdioMcpServerConfig {
    return {
        type: 'stdio',
        command: process.execPath,
        args: [getBridgeEntrypoint()],
        env: {
            HOGBOT_MCP_URL: url,
            HOGBOT_MCP_HEADERS_JSON: JSON.stringify(headers ?? {}),
        },
    }
}

function parseSerializedServers(serialized: string): Record<string, StdioMcpServerConfig> {
    const loaded = JSON.parse(serialized) as SerializedRemoteMcpServer[]
    if (!Array.isArray(loaded)) {
        throw new Error('POSTHOG_MCP_SERVERS_JSON must be a JSON array')
    }

    const servers: Record<string, StdioMcpServerConfig> = {}
    for (const server of loaded) {
        if (!server || typeof server !== 'object') {
            continue
        }
        if (!server.name || !server.url || (server.type !== 'http' && server.type !== 'sse')) {
            continue
        }

        const headers = server.headers
            ? Object.fromEntries(server.headers.map((header) => [header.name, header.value]))
            : undefined

        servers[server.name] = buildBridgeConfig(server.url, headers)
    }
    return servers
}

export function getPostHogMcpServersFromEnv(
    env: NodeJS.ProcessEnv = process.env
): Record<string, StdioMcpServerConfig> {
    if (env.POSTHOG_MCP_SERVERS_JSON) {
        return parseSerializedServers(env.POSTHOG_MCP_SERVERS_JSON)
    }

    if (!env.POSTHOG_MCP_URL || !env.POSTHOG_PERSONAL_API_KEY || !env.POSTHOG_PROJECT_ID) {
        return {}
    }

    return {
        posthog: buildBridgeConfig(env.POSTHOG_MCP_URL, {
            Authorization: `Bearer ${env.POSTHOG_PERSONAL_API_KEY}`,
            'x-posthog-project-id': env.POSTHOG_PROJECT_ID,
            'x-posthog-mcp-version': '2',
            'x-posthog-read-only': 'false',
        }),
    }
}
