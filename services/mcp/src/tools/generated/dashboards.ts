// AUTO-GENERATED from products/dashboards/mcp/tools.yaml + OpenAPI — do not edit
import { z } from 'zod'

import type { Schemas } from '@/api/generated'
import {
    DashboardsCreateBody,
    DashboardsDestroyParams,
    DashboardsListQueryParams,
    DashboardsPartialUpdateBody,
    DashboardsPartialUpdateParams,
    DashboardsRetrieveParams,
} from '@/generated/dashboards/api'
import { withPostHogUrl, type WithPostHogUrl } from '@/tools/tool-utils'
import type { Context, ToolBase, ZodObjectAny } from '@/tools/types'

const DashboardsGetAllSchema = DashboardsListQueryParams.omit({ format: true })

const dashboardsGetAll = (): ToolBase<
    typeof DashboardsGetAllSchema,
    WithPostHogUrl<Schemas.PaginatedDashboardBasicList>
> => ({
    name: 'dashboards-get-all',
    schema: DashboardsGetAllSchema,
    handler: async (context: Context, params: z.infer<typeof DashboardsGetAllSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.PaginatedDashboardBasicList>({
            method: 'GET',
            path: `/api/projects/${projectId}/dashboards/`,
            query: {
                limit: params.limit,
                offset: params.offset,
            },
        })
        return await withPostHogUrl(
            context,
            {
                ...result,
                results: await Promise.all(
                    result.results.map((item) => withPostHogUrl(context, item, `/dashboard/${item.id}`))
                ),
            },
            '/dashboard'
        )
    },
})

const DashboardCreateSchema = DashboardsCreateBody

const dashboardCreate = (): ToolBase<typeof DashboardCreateSchema, WithPostHogUrl<Schemas.Dashboard>> => ({
    name: 'dashboard-create',
    schema: DashboardCreateSchema,
    handler: async (context: Context, params: z.infer<typeof DashboardCreateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.name !== undefined) {
            body['name'] = params.name
        }
        if (params.description !== undefined) {
            body['description'] = params.description
        }
        if (params.pinned !== undefined) {
            body['pinned'] = params.pinned
        }
        if (params.breakdown_colors !== undefined) {
            body['breakdown_colors'] = params.breakdown_colors
        }
        if (params.data_color_theme_id !== undefined) {
            body['data_color_theme_id'] = params.data_color_theme_id
        }
        if (params.tags !== undefined) {
            body['tags'] = params.tags
        }
        if (params.restriction_level !== undefined) {
            body['restriction_level'] = params.restriction_level
        }
        if (params.use_template !== undefined) {
            body['use_template'] = params.use_template
        }
        if (params.use_dashboard !== undefined) {
            body['use_dashboard'] = params.use_dashboard
        }
        if (params.delete_insights !== undefined) {
            body['delete_insights'] = params.delete_insights
        }
        const result = await context.api.request<Schemas.Dashboard>({
            method: 'POST',
            path: `/api/projects/${projectId}/dashboards/`,
            body,
        })
        return await withPostHogUrl(context, result, `/dashboard/${result.id}`)
    },
})

const DashboardGetSchema = DashboardsRetrieveParams.omit({ project_id: true })

const dashboardGet = (): ToolBase<typeof DashboardGetSchema, WithPostHogUrl<Schemas.Dashboard>> => ({
    name: 'dashboard-get',
    schema: DashboardGetSchema,
    handler: async (context: Context, params: z.infer<typeof DashboardGetSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.Dashboard>({
            method: 'GET',
            path: `/api/projects/${projectId}/dashboards/${params.id}/`,
        })
        return await withPostHogUrl(context, result, `/dashboard/${result.id}`)
    },
})

const DashboardUpdateSchema = DashboardsPartialUpdateParams.omit({ project_id: true }).extend(
    DashboardsPartialUpdateBody.shape
)

const dashboardUpdate = (): ToolBase<typeof DashboardUpdateSchema, WithPostHogUrl<Schemas.Dashboard>> => ({
    name: 'dashboard-update',
    schema: DashboardUpdateSchema,
    handler: async (context: Context, params: z.infer<typeof DashboardUpdateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.name !== undefined) {
            body['name'] = params.name
        }
        if (params.description !== undefined) {
            body['description'] = params.description
        }
        if (params.pinned !== undefined) {
            body['pinned'] = params.pinned
        }
        if (params.breakdown_colors !== undefined) {
            body['breakdown_colors'] = params.breakdown_colors
        }
        if (params.data_color_theme_id !== undefined) {
            body['data_color_theme_id'] = params.data_color_theme_id
        }
        if (params.tags !== undefined) {
            body['tags'] = params.tags
        }
        if (params.restriction_level !== undefined) {
            body['restriction_level'] = params.restriction_level
        }
        if (params.use_template !== undefined) {
            body['use_template'] = params.use_template
        }
        if (params.use_dashboard !== undefined) {
            body['use_dashboard'] = params.use_dashboard
        }
        if (params.delete_insights !== undefined) {
            body['delete_insights'] = params.delete_insights
        }
        const result = await context.api.request<Schemas.Dashboard>({
            method: 'PATCH',
            path: `/api/projects/${projectId}/dashboards/${params.id}/`,
            body,
        })
        return await withPostHogUrl(context, result, `/dashboard/${result.id}`)
    },
})

const DashboardDeleteSchema = DashboardsDestroyParams.omit({ project_id: true })

const dashboardDelete = (): ToolBase<typeof DashboardDeleteSchema, Schemas.Dashboard> => ({
    name: 'dashboard-delete',
    schema: DashboardDeleteSchema,
    handler: async (context: Context, params: z.infer<typeof DashboardDeleteSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.Dashboard>({
            method: 'PATCH',
            path: `/api/projects/${projectId}/dashboards/${params.id}/`,
            body: { deleted: true },
        })
        return result
    },
})

export const GENERATED_TOOLS: Record<string, () => ToolBase<ZodObjectAny>> = {
    'dashboards-get-all': dashboardsGetAll,
    'dashboard-create': dashboardCreate,
    'dashboard-get': dashboardGet,
    'dashboard-update': dashboardUpdate,
    'dashboard-delete': dashboardDelete,
}
