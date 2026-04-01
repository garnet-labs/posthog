/**
 * Hand-coded query-llm-trace tool.
 *
 * Retrieves a single LLM trace by ID with configurable content detail level.
 * Defaults to "preview" which truncates large properties to first/last 300 chars.
 */
import { z } from 'zod'

import type { Context, ToolBase } from '@/tools/types'

import { AnyPropertyFilter, type ContentDetail, processTraceResults } from './traceContentProcessor'

const schema = z.object({
    traceId: z.string().describe('The trace ID to retrieve ($ai_trace_id value shared by all events in a trace)'),
    dateRange: z
        .object({
            date_from: z.string().nullish(),
            date_to: z.string().nullish(),
            explicitDate: z.boolean().default(false).optional(),
        })
        .optional()
        .describe('Date range for the query. Required — traces outside this range will not be found.'),
    properties: z.array(AnyPropertyFilter).optional().describe('Property filters to narrow results within the trace'),
    contentDetail: z
        .enum(['none', 'preview', 'full'])
        .default('preview')
        .describe(
            'Controls how much content is returned for large properties like $ai_input and $ai_output_choices. ' +
                '"none" returns metadata only with char counts. ' +
                '"preview" (default) returns first/last 300 chars of large properties. ' +
                '"full" returns everything — use with caution as traces can be very large.'
        ),
})

type Result = { results: unknown; _posthogUrl: string }

export default (): ToolBase<typeof schema, Result> => ({
    name: 'query-llm-trace',
    schema,
    handler: async (context: Context, params: z.infer<typeof schema>) => {
        const projectId = await context.stateManager.getProjectId()
        const contentDetail: ContentDetail = params.contentDetail ?? 'preview'
        const { contentDetail: _, ...queryParams } = params
        const query = { ...queryParams, kind: 'TraceQuery' }

        const result = await context.api.request<{ results: unknown; formatted_results?: string }>({
            method: 'POST',
            path: `/api/environments/${projectId}/query/`,
            body: { query },
        })

        const results = processTraceResults(result.formatted_results ?? result.results, contentDetail)

        const queryParam = encodeURIComponent(JSON.stringify(query))
        const baseUrl = context.api.getProjectBaseUrl(projectId)
        return {
            results,
            _posthogUrl: `${baseUrl}/insights/new?q=${queryParam}`,
        }
    },
})
