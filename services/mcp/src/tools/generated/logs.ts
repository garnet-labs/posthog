// AUTO-GENERATED from products/logs/mcp/tools.yaml + OpenAPI — do not edit
import { z } from 'zod'

import type { Schemas } from '@/api/generated'
import {
    LogsAlertsCreateBody,
    LogsAlertsDestroyParams,
    LogsAlertsListQueryParams,
    LogsAlertsPartialUpdateBody,
    LogsAlertsPartialUpdateParams,
    LogsAlertsRetrieveParams,
} from '@/generated/logs/api'
import type { Context, ToolBase, ZodObjectAny } from '@/tools/types'

const LogsAlertsListSchema = LogsAlertsListQueryParams

const logsAlertsList = (): ToolBase<
    typeof LogsAlertsListSchema,
    Schemas.PaginatedLogsAlertConfigurationList & { _posthogUrl: string }
> => ({
    name: 'logs-alerts-list',
    schema: LogsAlertsListSchema,
    handler: async (context: Context, params: z.infer<typeof LogsAlertsListSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.PaginatedLogsAlertConfigurationList>({
            method: 'GET',
            path: `/api/projects/${projectId}/logs/alerts/`,
            query: {
                limit: params.limit,
                offset: params.offset,
            },
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/logs`,
        }
    },
})

const LogsAlertsCreateSchema = LogsAlertsCreateBody

const logsAlertsCreate = (): ToolBase<typeof LogsAlertsCreateSchema, Schemas.LogsAlertConfiguration> => ({
    name: 'logs-alerts-create',
    schema: LogsAlertsCreateSchema,
    handler: async (context: Context, params: z.infer<typeof LogsAlertsCreateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.name !== undefined) {
            body['name'] = params.name
        }
        if (params.enabled !== undefined) {
            body['enabled'] = params.enabled
        }
        if (params.filters !== undefined) {
            body['filters'] = params.filters
        }
        if (params.threshold_count !== undefined) {
            body['threshold_count'] = params.threshold_count
        }
        if (params.threshold_operator !== undefined) {
            body['threshold_operator'] = params.threshold_operator
        }
        if (params.window_minutes !== undefined) {
            body['window_minutes'] = params.window_minutes
        }
        if (params.evaluation_periods !== undefined) {
            body['evaluation_periods'] = params.evaluation_periods
        }
        if (params.datapoints_to_alarm !== undefined) {
            body['datapoints_to_alarm'] = params.datapoints_to_alarm
        }
        if (params.cooldown_minutes !== undefined) {
            body['cooldown_minutes'] = params.cooldown_minutes
        }
        if (params.snooze_until !== undefined) {
            body['snooze_until'] = params.snooze_until
        }
        const result = await context.api.request<Schemas.LogsAlertConfiguration>({
            method: 'POST',
            path: `/api/projects/${projectId}/logs/alerts/`,
            body,
        })
        return result
    },
})

const LogsAlertsRetrieveSchema = LogsAlertsRetrieveParams.omit({ project_id: true })

const logsAlertsRetrieve = (): ToolBase<typeof LogsAlertsRetrieveSchema, Schemas.LogsAlertConfiguration> => ({
    name: 'logs-alerts-retrieve',
    schema: LogsAlertsRetrieveSchema,
    handler: async (context: Context, params: z.infer<typeof LogsAlertsRetrieveSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.LogsAlertConfiguration>({
            method: 'GET',
            path: `/api/projects/${projectId}/logs/alerts/${params.id}/`,
        })
        return result
    },
})

const LogsAlertsPartialUpdateSchema = LogsAlertsPartialUpdateParams.omit({ project_id: true }).extend(
    LogsAlertsPartialUpdateBody.shape
)

const logsAlertsPartialUpdate = (): ToolBase<typeof LogsAlertsPartialUpdateSchema, Schemas.LogsAlertConfiguration> => ({
    name: 'logs-alerts-partial-update',
    schema: LogsAlertsPartialUpdateSchema,
    handler: async (context: Context, params: z.infer<typeof LogsAlertsPartialUpdateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.name !== undefined) {
            body['name'] = params.name
        }
        if (params.enabled !== undefined) {
            body['enabled'] = params.enabled
        }
        if (params.filters !== undefined) {
            body['filters'] = params.filters
        }
        if (params.threshold_count !== undefined) {
            body['threshold_count'] = params.threshold_count
        }
        if (params.threshold_operator !== undefined) {
            body['threshold_operator'] = params.threshold_operator
        }
        if (params.window_minutes !== undefined) {
            body['window_minutes'] = params.window_minutes
        }
        if (params.evaluation_periods !== undefined) {
            body['evaluation_periods'] = params.evaluation_periods
        }
        if (params.datapoints_to_alarm !== undefined) {
            body['datapoints_to_alarm'] = params.datapoints_to_alarm
        }
        if (params.cooldown_minutes !== undefined) {
            body['cooldown_minutes'] = params.cooldown_minutes
        }
        if (params.snooze_until !== undefined) {
            body['snooze_until'] = params.snooze_until
        }
        const result = await context.api.request<Schemas.LogsAlertConfiguration>({
            method: 'PATCH',
            path: `/api/projects/${projectId}/logs/alerts/${params.id}/`,
            body,
        })
        return result
    },
})

const LogsAlertsDestroySchema = LogsAlertsDestroyParams.omit({ project_id: true })

const logsAlertsDestroy = (): ToolBase<typeof LogsAlertsDestroySchema, unknown> => ({
    name: 'logs-alerts-destroy',
    schema: LogsAlertsDestroySchema,
    handler: async (context: Context, params: z.infer<typeof LogsAlertsDestroySchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<unknown>({
            method: 'DELETE',
            path: `/api/projects/${projectId}/logs/alerts/${params.id}/`,
        })
        return result
    },
})

export const GENERATED_TOOLS: Record<string, () => ToolBase<ZodObjectAny>> = {
    'logs-alerts-list': logsAlertsList,
    'logs-alerts-create': logsAlertsCreate,
    'logs-alerts-retrieve': logsAlertsRetrieve,
    'logs-alerts-partial-update': logsAlertsPartialUpdate,
    'logs-alerts-destroy': logsAlertsDestroy,
}
