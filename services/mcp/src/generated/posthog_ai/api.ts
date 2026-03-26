/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 10 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const ActionPredictionConfigsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionPredictionConfigsListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

export const ActionPredictionConfigsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const actionPredictionConfigsCreateBodyNameMax = 400

export const actionPredictionConfigsCreateBodyEventNameMax = 400

export const ActionPredictionConfigsCreateBody = /* @__PURE__ */ zod.object({
    name: zod
        .string()
        .max(actionPredictionConfigsCreateBodyNameMax)
        .optional()
        .describe('Human-readable name for the prediction config.'),
    description: zod.string().optional().describe("Longer description of the prediction config's purpose."),
    action: zod.number().nullish().describe('ID of the PostHog action to predict. Mutually exclusive with event_name.'),
    event_name: zod
        .string()
        .max(actionPredictionConfigsCreateBodyEventNameMax)
        .nullish()
        .describe('Name of the raw event to predict. Mutually exclusive with action.'),
    lookback_days: zod.number().min(1).describe('Number of days to look back for prediction data.'),
    winning_model: zod
        .string()
        .nullish()
        .describe('The current winning model. Set by the agent after the experiment loop.'),
})

export const ActionPredictionConfigsRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this action prediction config.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionPredictionConfigsPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this action prediction config.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const actionPredictionConfigsPartialUpdateBodyNameMax = 400

export const actionPredictionConfigsPartialUpdateBodyEventNameMax = 400

export const ActionPredictionConfigsPartialUpdateBody = /* @__PURE__ */ zod.object({
    name: zod
        .string()
        .max(actionPredictionConfigsPartialUpdateBodyNameMax)
        .optional()
        .describe('Human-readable name for the prediction config.'),
    description: zod.string().optional().describe("Longer description of the prediction config's purpose."),
    action: zod.number().nullish().describe('ID of the PostHog action to predict. Mutually exclusive with event_name.'),
    event_name: zod
        .string()
        .max(actionPredictionConfigsPartialUpdateBodyEventNameMax)
        .nullish()
        .describe('Name of the raw event to predict. Mutually exclusive with action.'),
    lookback_days: zod.number().min(1).optional().describe('Number of days to look back for prediction data.'),
    winning_model: zod
        .string()
        .nullish()
        .describe('The current winning model. Set by the agent after the experiment loop.'),
})

export const ActionPredictionConfigsDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this action prediction config.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

/**
 * Returns a presigned POST URL that can be used to upload a model artifact directly to S3. Use the returned storage_path as model_url when creating an ActionPredictionModel.
 * @summary Generate a presigned S3 upload URL for a model artifact
 */
export const ActionPredictionConfigsUploadUrlCreateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this action prediction config.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
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

export const actionPredictionModelsCreateBodyModelUrlMax = 2000

export const ActionPredictionModelsCreateBody = /* @__PURE__ */ zod.object({
    config: zod.string(),
    experiment_id: zod.string().nullish().describe('Groups runs from the same agent experiment session.'),
    model_url: zod
        .string()
        .max(actionPredictionModelsCreateBodyModelUrlMax)
        .describe('S3 storage path to the serialized model artifact.'),
    metrics: zod.unknown().optional().describe('Model evaluation metrics (e.g. accuracy, AUC, F1).'),
    feature_importance: zod.unknown().optional().describe('Feature importance scores from model training.'),
    artifact_scripts: zod
        .unknown()
        .optional()
        .describe(
            'Self-contained scripts for this run. Keys: query (HogQL), utils (API helpers), train (training script), predict (scoring script).'
        ),
    notes: zod.string().optional().describe('Agent lab notebook: what was tried, what was observed, what to try next.'),
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

export const actionPredictionModelsPartialUpdateBodyModelUrlMax = 2000

export const ActionPredictionModelsPartialUpdateBody = /* @__PURE__ */ zod.object({
    config: zod.string().optional(),
    experiment_id: zod.string().nullish().describe('Groups runs from the same agent experiment session.'),
    model_url: zod
        .string()
        .max(actionPredictionModelsPartialUpdateBodyModelUrlMax)
        .optional()
        .describe('S3 storage path to the serialized model artifact.'),
    metrics: zod.unknown().optional().describe('Model evaluation metrics (e.g. accuracy, AUC, F1).'),
    feature_importance: zod.unknown().optional().describe('Feature importance scores from model training.'),
    artifact_scripts: zod
        .unknown()
        .optional()
        .describe(
            'Self-contained scripts for this run. Keys: query (HogQL), utils (API helpers), train (training script), predict (scoring script).'
        ),
    notes: zod.string().optional().describe('Agent lab notebook: what was tried, what was observed, what to try next.'),
})
