import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import type { CallToolResult } from '@modelcontextprotocol/sdk/types.js'
import MiniSearch from 'minisearch'
import { z } from 'zod'

import { hasScopes } from '@/lib/api'
import { formatResponse } from '@/lib/response'
import { GENERATED_TOOL_MAP } from '@/tools/generated'
import { TOOL_MAP } from '@/tools/index'
import { type ToolFilterOptions, getToolDefinitions, getToolsForFeatures } from '@/tools/toolDefinitions'
import type { Context, ToolBase, ZodObjectAny } from '@/tools/types'

interface ToolSearchDocument {
    id: string
    name: string
    title: string
    description: string
    summary: string
    category: string
    feature: string
}

function textResult(text: string): CallToolResult {
    return { content: [{ type: 'text', text }] }
}

function errorResult(text: string): CallToolResult {
    return { content: [{ type: 'text', text }], isError: true }
}

/**
 * Registers the 3 meta-tools (tool_search, tool_schema, tool_call) that let
 * LLM clients discover and invoke PostHog tools without loading all tool
 * schemas upfront. Respects the same filtering as normal mode (features, tools,
 * version, readOnly, OAuth scopes, AI consent).
 */
export async function registerToolSearchMode(
    server: McpServer,
    context: Context,
    options: ToolFilterOptions
): Promise<void> {
    const excludeTools = options.excludeTools ?? []
    const filteredNames = getToolsForFeatures(options).filter((name) => !excludeTools.includes(name))

    const apiKey = await context.stateManager.getApiKey()
    const scopes = apiKey?.scopes ?? []
    const definitions = getToolDefinitions(options.version)
    const allowedToolNames = new Set(
        filteredNames.filter((name) => {
            const def = definitions[name]
            return def && hasScopes(scopes, def.required_scopes)
        })
    )

    const searchIndex = new MiniSearch<ToolSearchDocument>({
        fields: ['name', 'title', 'description', 'summary', 'category', 'feature'],
        storeFields: ['name', 'title', 'summary', 'category', 'feature'],
        idField: 'id',
        searchOptions: {
            boost: { name: 3, title: 2, summary: 1.5 },
            fuzzy: 0.2,
            prefix: true,
            combineWith: 'AND',
        },
    })

    const documents: ToolSearchDocument[] = []
    for (const name of allowedToolNames) {
        const def = definitions[name]
        if (def) {
            documents.push({
                id: name,
                name,
                title: def.title,
                description: def.description,
                summary: def.summary,
                category: def.category,
                feature: def.feature,
            })
        }
    }
    searchIndex.addAll(documents)

    const effectiveMap = { ...TOOL_MAP, ...GENERATED_TOOL_MAP }

    // Lazy cache for tool factories and JSON schemas to avoid repeated
    // instantiation and schema conversion on every tool_schema/tool_call.
    const toolCache = new Map<string, ToolBase<ZodObjectAny>>()
    const schemaCache = new Map<string, object>()

    function getToolBase(toolName: string): ToolBase<ZodObjectAny> | undefined {
        let cached = toolCache.get(toolName)
        if (!cached) {
            const factory = effectiveMap[toolName]
            if (!factory) {
                return undefined
            }
            cached = factory()
            toolCache.set(toolName, cached)
        }
        return cached
    }

    function getJsonSchema(toolName: string, toolBase: ToolBase<ZodObjectAny>): object {
        let cached = schemaCache.get(toolName)
        if (!cached) {
            cached = z.toJSONSchema(toolBase.schema as z.ZodType, { io: 'input', reused: 'inline' })
            schemaCache.set(toolName, cached)
        }
        return cached
    }

    function resolveTool(toolName: string): { tool: ToolBase<ZodObjectAny> } | { error: CallToolResult } {
        if (!allowedToolNames.has(toolName)) {
            return {
                error: errorResult(`Error: Tool "${toolName}" not found. Use tool_search to find available tools.`),
            }
        }
        const tool = getToolBase(toolName)
        if (!tool) {
            return { error: errorResult(`Error: Tool "${toolName}" has no implementation.`) }
        }
        return { tool }
    }

    server.registerTool(
        'tool_search',
        {
            title: 'Search for PostHog tools',
            description:
                'Search for available PostHog tools by keyword. Use this to discover which tools are available before calling them. Returns matching tools with their names, summaries, and categories. Always start here when you need to interact with PostHog — search for what you need, then use tool_schema to get the full input schema, then use tool_call to execute.',
            inputSchema: {
                query: z
                    .string()
                    .describe('Search query to find PostHog tools (e.g., "feature flag", "dashboard", "experiment")'),
                limit: z.number().optional().default(10).describe('Maximum number of results to return'),
            },
            annotations: {
                readOnlyHint: true,
                idempotentHint: true,
                destructiveHint: false,
                openWorldHint: false,
            },
        },
        async ({ query, limit }) => {
            const results = searchIndex.search(query).slice(0, limit)
            const items = results.map((result) => ({
                name: result.id,
                title: result.title,
                summary: result.summary,
                category: result.category,
                feature: result.feature,
            }))
            return textResult(formatResponse(items))
        }
    )

    server.registerTool(
        'tool_schema',
        {
            title: 'Get tool input schema',
            description:
                'Get the full input schema for a specific PostHog tool. Returns the JSON Schema describing all accepted parameters, including required fields, types, and descriptions. Use this after tool_search to understand what parameters a tool needs before calling it with tool_call. Pass the exact tool name from tool_search results.',
            inputSchema: {
                tool_name: z.string().describe('Exact tool name from tool_search results'),
            },
            annotations: {
                readOnlyHint: true,
                idempotentHint: true,
                destructiveHint: false,
                openWorldHint: false,
            },
        },
        async ({ tool_name }) => {
            const resolved = resolveTool(tool_name)
            if ('error' in resolved) {
                return resolved.error
            }

            const def = definitions[tool_name]!
            return textResult(
                formatResponse({
                    name: tool_name,
                    title: def.title,
                    description: def.description,
                    annotations: def.annotations,
                    inputSchema: getJsonSchema(tool_name, resolved.tool),
                })
            )
        }
    )

    server.registerTool(
        'tool_call',
        {
            title: 'Call a PostHog tool',
            description:
                "Execute a PostHog tool by name with the given parameters. Use tool_search to find the right tool, then tool_schema to get its input schema, then this tool to call it. The params object must match the schema returned by tool_schema. Returns the tool's response.",
            inputSchema: {
                tool_name: z.string().describe('Exact tool name to call'),
                params: z
                    .record(z.string(), z.any())
                    .optional()
                    .default({})
                    .describe("Input parameters matching the tool's schema"),
            },
            annotations: {
                readOnlyHint: false,
                idempotentHint: false,
                destructiveHint: false,
                openWorldHint: true,
            },
        },
        async ({ tool_name, params }) => {
            const resolved = resolveTool(tool_name)
            if ('error' in resolved) {
                return resolved.error
            }

            const validation = (resolved.tool.schema as z.ZodType).safeParse(params)
            if (!validation.success) {
                return errorResult(`Invalid parameters for "${tool_name}": ${validation.error.message}`)
            }

            try {
                const result = await resolved.tool.handler(context, validation.data)
                return textResult(formatResponse(result))
            } catch (error: any) {
                const message = error instanceof Error ? error.message : String(error)
                return errorResult(`Error calling "${tool_name}": ${message}`)
            }
        }
    )
}
