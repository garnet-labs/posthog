/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 5 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const LlmPromptsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const LlmPromptsListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

export const LlmPromptsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const llmPromptsCreateBodyNameMax = 255

export const LlmPromptsCreateBody = /* @__PURE__ */ zod.object({
    name: zod.string().max(llmPromptsCreateBodyNameMax),
    prompt: zod.unknown(),
    deleted: zod.boolean().optional(),
})

export const llmPromptsNameRetrievePathPromptNameRegExp = new RegExp('^[^/]+$')

export const LlmPromptsNameRetrieveParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
    prompt_name: zod.string().regex(llmPromptsNameRetrievePathPromptNameRegExp),
})
