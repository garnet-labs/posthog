// AUTO-GENERATED from products/posthog_ai/mcp/tools.yaml + OpenAPI — do not edit
import { z } from 'zod'

import type { Schemas } from '@/api/generated'
import {
    ActionPredictionConfigsCreateBody,
    ActionPredictionConfigsDestroyParams,
    ActionPredictionConfigsListQueryParams,
    ActionPredictionConfigsPartialUpdateBody,
    ActionPredictionConfigsPartialUpdateParams,
    ActionPredictionConfigsRetrieveParams,
    ActionPredictionConfigsUploadUrlCreateParams,
    ActionPredictionModelRunsCreateBody,
    ActionPredictionModelRunsListQueryParams,
    ActionPredictionModelsCreateBody,
    ActionPredictionModelsListQueryParams,
} from '@/generated/posthog_ai/api'
import type { Context, ToolBase, ZodObjectAny } from '@/tools/types'

const ActionPredictionConfigListSchema = ActionPredictionConfigsListQueryParams

const actionPredictionConfigList = (): ToolBase<
    typeof ActionPredictionConfigListSchema,
    Schemas.PaginatedActionPredictionConfigList & { _posthogUrl: string }
> => ({
    name: 'action-prediction-config-list',
    schema: ActionPredictionConfigListSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionConfigListSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.PaginatedActionPredictionConfigList>({
            method: 'GET',
            path: `/api/environments/${projectId}/action_prediction_configs/`,
            query: {
                limit: params.limit,
                offset: params.offset,
            },
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_configs`,
        }
    },
})

const ActionPredictionConfigRetrieveSchema = ActionPredictionConfigsRetrieveParams.omit({ project_id: true })

const actionPredictionConfigRetrieve = (): ToolBase<
    typeof ActionPredictionConfigRetrieveSchema,
    Schemas.ActionPredictionConfig
> => ({
    name: 'action-prediction-config-retrieve',
    schema: ActionPredictionConfigRetrieveSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionConfigRetrieveSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.ActionPredictionConfig>({
            method: 'GET',
            path: `/api/environments/${projectId}/action_prediction_configs/${params.id}/`,
        })
        return result
    },
})

const ActionPredictionConfigCreateSchema = ActionPredictionConfigsCreateBody

const actionPredictionConfigCreate = (): ToolBase<
    typeof ActionPredictionConfigCreateSchema,
    Schemas.ActionPredictionConfig & { _posthogUrl: string }
> => ({
    name: 'action-prediction-config-create',
    schema: ActionPredictionConfigCreateSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionConfigCreateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.name !== undefined) {
            body['name'] = params.name
        }
        if (params.description !== undefined) {
            body['description'] = params.description
        }
        if (params.action !== undefined) {
            body['action'] = params.action
        }
        if (params.event_name !== undefined) {
            body['event_name'] = params.event_name
        }
        if (params.lookback_days !== undefined) {
            body['lookback_days'] = params.lookback_days
        }
        const result = await context.api.request<Schemas.ActionPredictionConfig>({
            method: 'POST',
            path: `/api/environments/${projectId}/action_prediction_configs/`,
            body,
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_configs/${(result as any).id}`,
        }
    },
})

const ActionPredictionConfigPartialUpdateSchema = ActionPredictionConfigsPartialUpdateParams.omit({
    project_id: true,
}).extend(ActionPredictionConfigsPartialUpdateBody.shape)

const actionPredictionConfigPartialUpdate = (): ToolBase<
    typeof ActionPredictionConfigPartialUpdateSchema,
    Schemas.ActionPredictionConfig & { _posthogUrl: string }
> => ({
    name: 'action-prediction-config-partial-update',
    schema: ActionPredictionConfigPartialUpdateSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionConfigPartialUpdateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.name !== undefined) {
            body['name'] = params.name
        }
        if (params.description !== undefined) {
            body['description'] = params.description
        }
        if (params.action !== undefined) {
            body['action'] = params.action
        }
        if (params.event_name !== undefined) {
            body['event_name'] = params.event_name
        }
        if (params.lookback_days !== undefined) {
            body['lookback_days'] = params.lookback_days
        }
        const result = await context.api.request<Schemas.ActionPredictionConfig>({
            method: 'PATCH',
            path: `/api/environments/${projectId}/action_prediction_configs/${params.id}/`,
            body,
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_configs/${(result as any).id}`,
        }
    },
})

const ActionPredictionConfigDestroySchema = ActionPredictionConfigsDestroyParams.omit({ project_id: true })

const actionPredictionConfigDestroy = (): ToolBase<typeof ActionPredictionConfigDestroySchema, unknown> => ({
    name: 'action-prediction-config-destroy',
    schema: ActionPredictionConfigDestroySchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionConfigDestroySchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<unknown>({
            method: 'DELETE',
            path: `/api/environments/${projectId}/action_prediction_configs/${params.id}/`,
        })
        return result
    },
})

const ActionPredictionConfigUploadUrlSchema = ActionPredictionConfigsUploadUrlCreateParams.omit({ project_id: true })

const actionPredictionConfigUploadUrl = (): ToolBase<
    typeof ActionPredictionConfigUploadUrlSchema,
    Schemas.UploadURLResponse
> => ({
    name: 'action-prediction-config-upload-url',
    schema: ActionPredictionConfigUploadUrlSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionConfigUploadUrlSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.UploadURLResponse>({
            method: 'POST',
            path: `/api/environments/${projectId}/action_prediction_configs/${params.id}/upload_url/`,
        })
        return result
    },
})

const ActionPredictionModelListSchema = ActionPredictionModelsListQueryParams

const actionPredictionModelList = (): ToolBase<
    typeof ActionPredictionModelListSchema,
    Schemas.PaginatedActionPredictionModelList & { _posthogUrl: string }
> => ({
    name: 'action-prediction-model-list',
    schema: ActionPredictionModelListSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionModelListSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.PaginatedActionPredictionModelList>({
            method: 'GET',
            path: `/api/environments/${projectId}/action_prediction_models/`,
            query: {
                limit: params.limit,
                offset: params.offset,
            },
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_configs`,
        }
    },
})

const ActionPredictionModelRetrieveSchema = ActionPredictionModelsRetrieveParams.omit({ project_id: true })

const actionPredictionModelRetrieve = (): ToolBase<
    typeof ActionPredictionModelRetrieveSchema,
    Schemas.ActionPredictionModel
> => ({
    name: 'action-prediction-model-retrieve',
    schema: ActionPredictionModelRetrieveSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionModelRetrieveSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.ActionPredictionModel>({
            method: 'GET',
            path: `/api/environments/${projectId}/action_prediction_models/${params.id}/`,
        })
        return result
    },
})

const ActionPredictionModelCreateSchema = ActionPredictionModelsCreateBody

const actionPredictionModelCreate = (): ToolBase<
    typeof ActionPredictionModelCreateSchema,
    Schemas.ActionPredictionModel & { _posthogUrl: string }
> => ({
    name: 'action-prediction-model-create',
    schema: ActionPredictionModelCreateSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionModelCreateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.config !== undefined) {
            body['config'] = params.config
        }
        if (params.task !== undefined) {
            body['task'] = params.task
        }
        if (params.task_run !== undefined) {
            body['task_run'] = params.task_run
        }
        if (params.is_winning !== undefined) {
            body['is_winning'] = params.is_winning
        }
        if (params.model_url !== undefined) {
            body['model_url'] = params.model_url
        }
        if (params.metrics !== undefined) {
            body['metrics'] = params.metrics
        }
        if (params.feature_importance !== undefined) {
            body['feature_importance'] = params.feature_importance
        }
        if (params.artifact_script !== undefined) {
            body['artifact_script'] = params.artifact_script
        }
        const result = await context.api.request<Schemas.ActionPredictionModel>({
            method: 'POST',
            path: `/api/environments/${projectId}/action_prediction_models/`,
            body,
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_configs/${(result as any).id}`,
        }
    },
})

const ActionPredictionModelPartialUpdateSchema = ActionPredictionModelsPartialUpdateParams.omit({
    project_id: true,
}).extend(ActionPredictionModelsPartialUpdateBody.omit({ config: true }).shape)

const actionPredictionModelPartialUpdate = (): ToolBase<
    typeof ActionPredictionModelPartialUpdateSchema,
    Schemas.ActionPredictionModel & { _posthogUrl: string }
> => ({
    name: 'action-prediction-model-partial-update',
    schema: ActionPredictionModelPartialUpdateSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionModelPartialUpdateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.task !== undefined) {
            body['task'] = params.task
        }
        if (params.task_run !== undefined) {
            body['task_run'] = params.task_run
        }
        if (params.is_winning !== undefined) {
            body['is_winning'] = params.is_winning
        }
        if (params.model_url !== undefined) {
            body['model_url'] = params.model_url
        }
        if (params.metrics !== undefined) {
            body['metrics'] = params.metrics
        }
        if (params.feature_importance !== undefined) {
            body['feature_importance'] = params.feature_importance
        }
        if (params.artifact_script !== undefined) {
            body['artifact_script'] = params.artifact_script
        }
        const result = await context.api.request<Schemas.ActionPredictionModel>({
            method: 'PATCH',
            path: `/api/environments/${projectId}/action_prediction_models/${params.id}/`,
            body,
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_configs/${(result as any).id}`,
        }
    },
})

export const GENERATED_TOOLS: Record<string, () => ToolBase<ZodObjectAny>> = {
    'action-prediction-config-list': actionPredictionConfigList,
    'action-prediction-config-retrieve': actionPredictionConfigRetrieve,
    'action-prediction-config-create': actionPredictionConfigCreate,
    'action-prediction-config-partial-update': actionPredictionConfigPartialUpdate,
    'action-prediction-config-destroy': actionPredictionConfigDestroy,
    'action-prediction-config-upload-url': actionPredictionConfigUploadUrl,
    'action-prediction-model-list': actionPredictionModelList,
    'action-prediction-model-create': actionPredictionModelCreate,
    'action-prediction-model-partial-update': actionPredictionModelPartialUpdate,
}
