// AUTO-GENERATED from products/logs/mcp/tools.yaml + OpenAPI — do not edit
import { z } from 'zod'

import {
    LogsAttributesRetrieveQueryParams,
    LogsQueryCreateBody,
    LogsValuesRetrieveQueryParams,
} from '@/generated/logs/api'
import { pickResponseFields } from '@/tools/tool-utils'
import type { Context, ToolBase, ZodObjectAny } from '@/tools/types'

const LogsQuerySchema = LogsQueryCreateBody

const logsQuery = (): ToolBase<typeof LogsQuerySchema, unknown> => ({
    name: 'logs-query',
    schema: LogsQuerySchema,
    handler: async (context: Context, params: z.infer<typeof LogsQuerySchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.query !== undefined) {
            body['query'] = params.query
        }
        const result = await context.api.request<unknown>({
            method: 'POST',
            path: `/api/projects/${projectId}/logs/query/`,
            body,
        })
        const filtered = pickResponseFields(result, ['results']) as typeof result
        return filtered
    },
})

const LogsListAttributesSchema = LogsAttributesRetrieveQueryParams

const logsListAttributes = (): ToolBase<typeof LogsListAttributesSchema, unknown> => ({
    name: 'logs-list-attributes',
    schema: LogsListAttributesSchema,
    handler: async (context: Context, params: z.infer<typeof LogsListAttributesSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<unknown>({
            method: 'GET',
            path: `/api/projects/${projectId}/logs/attributes/`,
            query: {
                attribute_type: params.attribute_type,
                limit: params.limit,
                offset: params.offset,
                search: params.search,
            },
        })
        const filtered = pickResponseFields(result, ['results', 'count']) as typeof result
        return filtered
    },
})

const LogsListAttributeValuesSchema = LogsValuesRetrieveQueryParams

const logsListAttributeValues = (): ToolBase<typeof LogsListAttributeValuesSchema, unknown> => ({
    name: 'logs-list-attribute-values',
    schema: LogsListAttributeValuesSchema,
    handler: async (context: Context, params: z.infer<typeof LogsListAttributeValuesSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<unknown>({
            method: 'GET',
            path: `/api/projects/${projectId}/logs/values/`,
            query: {
                attribute_type: params.attribute_type,
                key: params.key,
                value: params.value,
            },
        })
        const filtered = pickResponseFields(result, ['results']) as typeof result
        return filtered
    },
})

export const GENERATED_TOOLS: Record<string, () => ToolBase<ZodObjectAny>> = {
    'logs-query': logsQuery,
    'logs-list-attributes': logsListAttributes,
    'logs-list-attribute-values': logsListAttributeValues,
}
