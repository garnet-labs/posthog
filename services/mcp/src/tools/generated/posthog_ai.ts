// AUTO-GENERATED from products/posthog_ai/mcp/tools.yaml + OpenAPI — do not edit
import { z } from 'zod'

import type { Schemas } from '@/api/generated'
import {
    ActionPredictionModelRunsCreateBody,
    ActionPredictionModelRunsListQueryParams,
    ActionPredictionModelRunsPartialUpdateBody,
    ActionPredictionModelRunsPartialUpdateParams,
    ActionPredictionModelRunsRetrieveParams,
    ActionPredictionModelsCreateBody,
    ActionPredictionModelsDestroyParams,
    ActionPredictionModelsListQueryParams,
    ActionPredictionModelsPartialUpdateBody,
    ActionPredictionModelsPartialUpdateParams,
    ActionPredictionModelsRetrieveParams,
} from '@/generated/posthog_ai/api'
import type { Context, ToolBase, ZodObjectAny } from '@/tools/types'

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
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_models`,
        }
    },
})

const ActionPredictionModelRetrieveSchema = ActionPredictionModelsRetrieveParams.omit({ project_id: true })

const actionPredictionModelRetrieve = (): ToolBase<
    typeof ActionPredictionModelRetrieveSchema,
    Schemas.ActionPredictionModel & { _posthogUrl: string }
> => ({
    name: 'action-prediction-model-retrieve',
    schema: ActionPredictionModelRetrieveSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionModelRetrieveSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.ActionPredictionModel>({
            method: 'GET',
            path: `/api/environments/${projectId}/action_prediction_models/${params.id}/`,
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_models/${(result as any).id}`,
        }
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
        const result = await context.api.request<Schemas.ActionPredictionModel>({
            method: 'POST',
            path: `/api/environments/${projectId}/action_prediction_models/`,
            body,
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_models/${(result as any).id}`,
        }
    },
})

const ActionPredictionModelPartialUpdateSchema = ActionPredictionModelsPartialUpdateParams.omit({
    project_id: true,
}).extend(ActionPredictionModelsPartialUpdateBody.shape)

const actionPredictionModelPartialUpdate = (): ToolBase<
    typeof ActionPredictionModelPartialUpdateSchema,
    Schemas.ActionPredictionModel & { _posthogUrl: string }
> => ({
    name: 'action-prediction-model-partial-update',
    schema: ActionPredictionModelPartialUpdateSchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionModelPartialUpdateSchema>) => {
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
        const result = await context.api.request<Schemas.ActionPredictionModel>({
            method: 'PATCH',
            path: `/api/environments/${projectId}/action_prediction_models/${params.id}/`,
            body,
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_models/${(result as any).id}`,
        }
    },
})

const ActionPredictionModelDestroySchema = ActionPredictionModelsDestroyParams.omit({ project_id: true })

const actionPredictionModelDestroy = (): ToolBase<typeof ActionPredictionModelDestroySchema, unknown> => ({
    name: 'action-prediction-model-destroy',
    schema: ActionPredictionModelDestroySchema,
    handler: async (context: Context, params: z.infer<typeof ActionPredictionModelDestroySchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<unknown>({
            method: 'DELETE',
            path: `/api/environments/${projectId}/action_prediction_models/${params.id}/`,
        })
        return result
    },
})

const PredictionModelRunListSchema = ActionPredictionModelRunsListQueryParams

const predictionModelRunList = (): ToolBase<
    typeof PredictionModelRunListSchema,
    Schemas.PaginatedActionPredictionModelRunList & { _posthogUrl: string }
> => ({
    name: 'prediction-model-run-list',
    schema: PredictionModelRunListSchema,
    handler: async (context: Context, params: z.infer<typeof PredictionModelRunListSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.PaginatedActionPredictionModelRunList>({
            method: 'GET',
            path: `/api/environments/${projectId}/action_prediction_model_runs/`,
            query: {
                limit: params.limit,
                offset: params.offset,
            },
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_models`,
        }
    },
})

const PredictionModelRunRetrieveSchema = ActionPredictionModelRunsRetrieveParams.omit({ project_id: true })

const predictionModelRunRetrieve = (): ToolBase<
    typeof PredictionModelRunRetrieveSchema,
    Schemas.ActionPredictionModelRun & { _posthogUrl: string }
> => ({
    name: 'prediction-model-run-retrieve',
    schema: PredictionModelRunRetrieveSchema,
    handler: async (context: Context, params: z.infer<typeof PredictionModelRunRetrieveSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.ActionPredictionModelRun>({
            method: 'GET',
            path: `/api/environments/${projectId}/action_prediction_model_runs/${params.id}/`,
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_models/${(result as any).id}`,
        }
    },
})

const PredictionModelRunCreateSchema = ActionPredictionModelRunsCreateBody

const predictionModelRunCreate = (): ToolBase<
    typeof PredictionModelRunCreateSchema,
    Schemas.ActionPredictionModelRun & { _posthogUrl: string }
> => ({
    name: 'prediction-model-run-create',
    schema: PredictionModelRunCreateSchema,
    handler: async (context: Context, params: z.infer<typeof PredictionModelRunCreateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.prediction_model !== undefined) {
            body['prediction_model'] = params.prediction_model
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
        const result = await context.api.request<Schemas.ActionPredictionModelRun>({
            method: 'POST',
            path: `/api/environments/${projectId}/action_prediction_model_runs/`,
            body,
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_models/${(result as any).id}`,
        }
    },
})

const PredictionModelRunPartialUpdateSchema = ActionPredictionModelRunsPartialUpdateParams.omit({
    project_id: true,
}).extend(ActionPredictionModelRunsPartialUpdateBody.omit({ prediction_model: true }).shape)

const predictionModelRunPartialUpdate = (): ToolBase<
    typeof PredictionModelRunPartialUpdateSchema,
    Schemas.ActionPredictionModelRun & { _posthogUrl: string }
> => ({
    name: 'prediction-model-run-partial-update',
    schema: PredictionModelRunPartialUpdateSchema,
    handler: async (context: Context, params: z.infer<typeof PredictionModelRunPartialUpdateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
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
        const result = await context.api.request<Schemas.ActionPredictionModelRun>({
            method: 'PATCH',
            path: `/api/environments/${projectId}/action_prediction_model_runs/${params.id}/`,
            body,
        })
        return {
            ...(result as any),
            _posthogUrl: `${context.api.getProjectBaseUrl(projectId)}/action_prediction_models/${(result as any).id}`,
        }
    },
})

export const GENERATED_TOOLS: Record<string, () => ToolBase<ZodObjectAny>> = {
    'action-prediction-model-list': actionPredictionModelList,
    'action-prediction-model-retrieve': actionPredictionModelRetrieve,
    'action-prediction-model-create': actionPredictionModelCreate,
    'action-prediction-model-partial-update': actionPredictionModelPartialUpdate,
    'action-prediction-model-destroy': actionPredictionModelDestroy,
    'prediction-model-run-list': predictionModelRunList,
    'prediction-model-run-retrieve': predictionModelRunRetrieve,
    'prediction-model-run-create': predictionModelRunCreate,
    'prediction-model-run-partial-update': predictionModelRunPartialUpdate,
}
