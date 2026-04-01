/**
 * Hand-coded query-llm-traces-list tool.
 *
 * Always strips large content properties (contentDetail: "none") since
 * listing traces should be lightweight. Use query-llm-trace to inspect
 * individual traces with more detail.
 */
import { z } from 'zod'

import type { Context, ToolBase } from '@/tools/types'

import { AnyPropertyFilter, processTraceResults } from './traceContentProcessor'

const schema = z.object({
    dateRange: z
        .object({
            date_from: z.string().nullish(),
            date_to: z.string().nullish(),
            explicitDate: z.boolean().default(false).optional(),
        })
        .optional()
        .describe('Date range for the query'),
    limit: z.number().int().optional().describe('Maximum number of traces to return (default 100)'),
    offset: z.number().int().optional().describe('Number of traces to skip for pagination'),
    filterTestAccounts: z.boolean().optional().describe('Exclude internal and test users'),
    filterSupportTraces: z.boolean().optional().describe('Exclude support impersonation traces'),
    properties: z
        .array(AnyPropertyFilter)
        .optional()
        .describe(
            'Property filters to narrow results. Use event properties like $ai_model, $ai_provider, $ai_trace_id, etc.'
        ),
    personId: z.string().optional().describe('Filter traces by a specific person UUID'),
    groupKey: z.string().optional().describe('Filter traces by group key (requires groupTypeIndex)'),
    groupTypeIndex: z.number().int().optional().describe('Group type index when filtering by group'),
    randomOrder: z
        .boolean()
        .optional()
        .describe('Use random ordering instead of newest-first (useful for representative sampling)'),
})

type Result = { results: unknown; _posthogUrl: string }

export default (): ToolBase<typeof schema, Result> => ({
    name: 'query-llm-traces-list',
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
