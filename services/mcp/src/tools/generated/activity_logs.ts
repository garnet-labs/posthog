// AUTO-GENERATED from services/mcp/definitions/activity_logs.yaml + OpenAPI — do not edit
import { z } from 'zod'

import type { Schemas } from '@/api/generated'
import { withPostHogUrl, type WithPostHogUrl } from '@/tools/tool-utils'
import type { Context, ToolBase, ZodObjectAny } from '@/tools/types'

const ActivityLogsListSchema = z.object({})

const activityLogsList = (): ToolBase<
    typeof ActivityLogsListSchema,
    WithPostHogUrl<Schemas.PaginatedActivityLogList>
> => ({
    name: 'activity-logs-list',
    schema: ActivityLogsListSchema,
    // eslint-disable-next-line no-unused-vars
    handler: async (context: Context, params: z.infer<typeof ActivityLogsListSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.PaginatedActivityLogList>({
            method: 'GET',
            path: `/api/projects/${projectId}/activity_log/`,
        })
        return await withPostHogUrl(context, result, '/activity-logs')
    },
})

export const GENERATED_TOOLS: Record<string, () => ToolBase<ZodObjectAny>> = {
    'activity-logs-list': activityLogsList,
}
