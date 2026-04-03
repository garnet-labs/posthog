/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 5 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

/**
 * Create, Read, Update and Delete annotations. [See docs](https://posthog.com/docs/data/annotations) for more information on annotations.
 */
export const AnnotationsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const AnnotationsListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
    search: zod.string().optional().describe('A search term.'),
})

/**
 * Create, Read, Update and Delete annotations. [See docs](https://posthog.com/docs/data/annotations) for more information on annotations.
 */
export const AnnotationsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const annotationsCreateBodyContentMax = 8192

export const AnnotationsCreateBody = /* @__PURE__ */ zod.object({
    content: zod.string().max(annotationsCreateBodyContentMax).nullish(),
    date_marker: zod.iso.datetime({}).nullish(),
    creation_type: zod.enum(['USR', 'GIT']).optional().describe('* `USR` - user\n* `GIT` - GitHub'),
    dashboard_item: zod.number().nullish(),
    dashboard_id: zod.number().nullish(),
    deleted: zod.boolean().optional(),
    scope: zod
        .enum(['dashboard_item', 'dashboard', 'project', 'organization', 'recording'])
        .optional()
        .describe(
            '* `dashboard_item` - insight\n* `dashboard` - dashboard\n* `project` - project\n* `organization` - organization\n* `recording` - recording'
        ),
})

/**
 * Create, Read, Update and Delete annotations. [See docs](https://posthog.com/docs/data/annotations) for more information on annotations.
 */
export const AnnotationsRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this annotation.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

/**
 * Create, Read, Update and Delete annotations. [See docs](https://posthog.com/docs/data/annotations) for more information on annotations.
 */
export const AnnotationsPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this annotation.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const annotationsPartialUpdateBodyContentMax = 8192

export const AnnotationsPartialUpdateBody = /* @__PURE__ */ zod.object({
    content: zod.string().max(annotationsPartialUpdateBodyContentMax).nullish(),
    date_marker: zod.iso.datetime({}).nullish(),
    creation_type: zod.enum(['USR', 'GIT']).optional().describe('* `USR` - user\n* `GIT` - GitHub'),
    dashboard_item: zod.number().nullish(),
    dashboard_id: zod.number().nullish(),
    deleted: zod.boolean().optional(),
    scope: zod
        .enum(['dashboard_item', 'dashboard', 'project', 'organization', 'recording'])
        .optional()
        .describe(
            '* `dashboard_item` - insight\n* `dashboard` - dashboard\n* `project` - project\n* `organization` - organization\n* `recording` - recording'
        ),
})

/**
 * Hard delete of this model is not allowed. Use a patch API call to set "deleted" to true
 */
export const AnnotationsDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this annotation.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})
