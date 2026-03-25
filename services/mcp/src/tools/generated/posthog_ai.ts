// AUTO-GENERATED from products/posthog_ai/mcp/tools.yaml + OpenAPI — do not edit
import { z } from 'zod'

import type { Schemas } from '@/api/generated'
import {
    ActionPredictionModelRunsCreateBody,
    ActionPredictionModelRunsListQueryParams,
    ActionPredictionModelsCreateBody,
    ActionPredictionModelsListQueryParams,
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

export const GENERATED_TOOLS: Record<string, () => ToolBase<ZodObjectAny>> = {
    'action-prediction-model-list': actionPredictionModelList,
    'action-prediction-model-create': actionPredictionModelCreate,
    'prediction-model-run-list': predictionModelRunList,
    'prediction-model-run-create': predictionModelRunCreate,
}
