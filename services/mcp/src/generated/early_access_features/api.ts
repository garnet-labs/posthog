/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 5 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const EarlyAccessFeatureListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const EarlyAccessFeatureListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

export const EarlyAccessFeatureCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const earlyAccessFeatureCreateBodyNameMax = 200

export const earlyAccessFeatureCreateBodyDocumentationUrlMax = 800

export const EarlyAccessFeatureCreateBody = /* @__PURE__ */ zod.object({
    name: zod.string().max(earlyAccessFeatureCreateBodyNameMax),
    description: zod.string().optional(),
    stage: zod
        .enum(['draft', 'concept', 'alpha', 'beta', 'general-availability', 'archived'])
        .describe(
            '* `draft` - draft\n* `concept` - concept\n* `alpha` - alpha\n* `beta` - beta\n* `general-availability` - general availability\n* `archived` - archived'
        ),
    documentation_url: zod.url().max(earlyAccessFeatureCreateBodyDocumentationUrlMax).optional(),
    payload: zod.unknown().optional(),
    feature_flag_id: zod.number().optional(),
    _create_in_folder: zod.string().optional(),
})

export const EarlyAccessFeatureRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this early access feature.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const EarlyAccessFeaturePartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this early access feature.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const earlyAccessFeaturePartialUpdateBodyNameMax = 200

export const earlyAccessFeaturePartialUpdateBodyDocumentationUrlMax = 800

export const EarlyAccessFeaturePartialUpdateBody = /* @__PURE__ */ zod.object({
    name: zod.string().max(earlyAccessFeaturePartialUpdateBodyNameMax).optional(),
    description: zod.string().optional(),
    stage: zod
        .enum(['draft', 'concept', 'alpha', 'beta', 'general-availability', 'archived'])
        .optional()
        .describe(
            '* `draft` - draft\n* `concept` - concept\n* `alpha` - alpha\n* `beta` - beta\n* `general-availability` - general availability\n* `archived` - archived'
        ),
    documentation_url: zod.url().max(earlyAccessFeaturePartialUpdateBodyDocumentationUrlMax).optional(),
})

export const EarlyAccessFeatureDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this early access feature.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})
