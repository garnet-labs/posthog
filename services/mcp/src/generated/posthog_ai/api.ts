/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 9 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const ActionPredictionModelRunsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionPredictionModelRunsListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

export const ActionPredictionModelRunsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const actionPredictionModelRunsCreateBodyModelUrlMax = 2000

export const ActionPredictionModelRunsCreateBody = /* @__PURE__ */ zod.object({
    prediction_model: zod.string(),
    is_winning: zod.boolean().optional().describe('Whether this run produced a winning prediction model.'),
    model_url: zod
        .url()
        .max(actionPredictionModelRunsCreateBodyModelUrlMax)
        .describe('S3 URL to the serialized model artifact.'),
    metrics: zod.unknown().optional().describe('Model evaluation metrics (e.g. accuracy, AUC, F1).'),
    feature_importance: zod.unknown().optional().describe('Feature importance scores from model training.'),
    artifact_script: zod
        .string()
        .optional()
        .describe('The Python script used to train and produce the model artifact.'),
})

export const ActionPredictionModelRunsRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this action prediction model run.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionPredictionModelRunsPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this action prediction model run.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const actionPredictionModelRunsPartialUpdateBodyModelUrlMax = 2000

export const ActionPredictionModelRunsPartialUpdateBody = /* @__PURE__ */ zod.object({
    prediction_model: zod.string().optional(),
    is_winning: zod.boolean().optional().describe('Whether this run produced a winning prediction model.'),
    model_url: zod
        .url()
        .max(actionPredictionModelRunsPartialUpdateBodyModelUrlMax)
        .optional()
        .describe('S3 URL to the serialized model artifact.'),
    metrics: zod.unknown().optional().describe('Model evaluation metrics (e.g. accuracy, AUC, F1).'),
    feature_importance: zod.unknown().optional().describe('Feature importance scores from model training.'),
    artifact_script: zod
        .string()
        .optional()
        .describe('The Python script used to train and produce the model artifact.'),
})

export const ActionPredictionModelsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionPredictionModelsListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

export const ActionPredictionModelsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const actionPredictionModelsCreateBodyNameMax = 400

export const actionPredictionModelsCreateBodyEventNameMax = 400

export const ActionPredictionModelsCreateBody = /* @__PURE__ */ zod.object({
    name: zod
        .string()
        .max(actionPredictionModelsCreateBodyNameMax)
        .optional()
        .describe('Human-readable name for the prediction model.'),
    description: zod.string().optional().describe("Longer description of the prediction model's purpose."),
    action: zod.number().nullish().describe('ID of the PostHog action to predict. Mutually exclusive with event_name.'),
    event_name: zod
        .string()
        .max(actionPredictionModelsCreateBodyEventNameMax)
        .nullish()
        .describe('Name of the raw event to predict. Mutually exclusive with action.'),
    lookback_days: zod.number().min(1).describe('Number of days to look back for prediction data.'),
})

export const ActionPredictionModelsRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this action prediction model.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionPredictionModelsPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this action prediction model.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const actionPredictionModelsPartialUpdateBodyNameMax = 400

export const actionPredictionModelsPartialUpdateBodyEventNameMax = 400

export const ActionPredictionModelsPartialUpdateBody = /* @__PURE__ */ zod.object({
    name: zod
        .string()
        .max(actionPredictionModelsPartialUpdateBodyNameMax)
        .optional()
        .describe('Human-readable name for the prediction model.'),
    description: zod.string().optional().describe("Longer description of the prediction model's purpose."),
    action: zod.number().nullish().describe('ID of the PostHog action to predict. Mutually exclusive with event_name.'),
    event_name: zod
        .string()
        .max(actionPredictionModelsPartialUpdateBodyEventNameMax)
        .nullish()
        .describe('Name of the raw event to predict. Mutually exclusive with action.'),
    lookback_days: zod.number().min(1).optional().describe('Number of days to look back for prediction data.'),
})

export const ActionPredictionModelsDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this action prediction model.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})
