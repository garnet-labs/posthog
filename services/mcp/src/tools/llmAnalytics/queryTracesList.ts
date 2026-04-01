/**
 * Hand-coded query-traces-list tool.
 *
 * Always strips large content properties (contentDetail: "none") since
 * listing traces should be lightweight. Use query-trace to inspect
 * individual traces with more detail.
 */
import { z } from 'zod'

import type { Context, ToolBase } from '@/tools/types'

import { processTraceResults } from './traceContentProcessor'

const schema = z.object({
    dateRange: z
        .object({
            date_from: z.string().nullish(),
            date_to: z.string().nullish(),
        })
        .optional(),
    limit: z.number().int().optional(),
    offset: z.number().int().optional(),
    filterTestAccounts: z.boolean().optional(),
    filterSupportTraces: z.boolean().optional(),
    properties: z
        .array(z.record(z.string(), z.unknown()))
        .optional()
        .describe('Properties configurable in the interface'),
    personId: z.string().optional().describe('Person who performed the event'),
    groupKey: z.string().optional(),
    groupTypeIndex: z.number().int().optional(),
})

type Result = { results: unknown; _posthogUrl: string }

export default (): ToolBase<typeof schema, Result> => ({
    name: 'query-traces-list',
    schema,
    handler: async (context: Context, params: z.infer<typeof schema>) => {
        const projectId = await context.stateManager.getProjectId()
        const query = { ...params, kind: 'TracesQuery' }

        const result = await context.api.request<{ results: unknown; formatted_results?: string }>({
            method: 'POST',
            path: `/api/environments/${projectId}/query/`,
            body: { query },
        })

        const results = processTraceResults(result.formatted_results ?? result.results, 'none')

        const queryParam = encodeURIComponent(JSON.stringify(query))
        const baseUrl = context.api.getProjectBaseUrl(projectId)
        return {
            results,
            _posthogUrl: `${baseUrl}/insights/new?q=${queryParam}`,
        }
    },
})
