/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 5 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const ActionsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionsListQueryParams = /* @__PURE__ */ zod.object({
    format: zod.enum(['csv', 'json']).optional(),
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

export const ActionsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionsCreateQueryParams = /* @__PURE__ */ zod.object({
    format: zod.enum(['csv', 'json']).optional(),
})

export const actionsCreateBodyNameMax = 400

export const actionsCreateBodySlackMessageFormatMax = 1200

export const ActionsCreateBody = /* @__PURE__ */ zod
    .object({
        name: zod.string().max(actionsCreateBodyNameMax).nullish(),
        description: zod.string().optional(),
        tags: zod.array(zod.unknown()).optional(),
        post_to_slack: zod.boolean().optional(),
        slack_message_format: zod.string().max(actionsCreateBodySlackMessageFormatMax).optional(),
        steps: zod
            .array(
                zod.object({
                    event: zod.string().nullish(),
                    properties: zod.array(zod.record(zod.string(), zod.unknown())).nullish(),
                    selector: zod.string().nullish(),
                    selector_regex: zod.string().nullish(),
                    tag_name: zod.string().nullish(),
                    text: zod.string().nullish(),
                    text_matching: zod
                        .union([
                            zod
                                .enum(['contains', 'regex', 'exact'])
                                .describe('* `contains` - contains\n* `regex` - regex\n* `exact` - exact'),
                            zod.literal(null),
                        ])
                        .nullish(),
                    href: zod.string().nullish(),
                    href_matching: zod
                        .union([
                            zod
                                .enum(['contains', 'regex', 'exact'])
                                .describe('* `contains` - contains\n* `regex` - regex\n* `exact` - exact'),
                            zod.literal(null),
                        ])
                        .nullish(),
                    url: zod.string().nullish(),
                    url_matching: zod
                        .union([
                            zod
                                .enum(['contains', 'regex', 'exact'])
                                .describe('* `contains` - contains\n* `regex` - regex\n* `exact` - exact'),
                            zod.literal(null),
                        ])
                        .nullish(),
                })
            )
            .optional(),
        pinned_at: zod.iso.datetime({}).nullish(),
        _create_in_folder: zod.string().optional(),
    })
    .describe('Serializer mixin that handles tags for objects.')

export const ActionsRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this action.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionsRetrieveQueryParams = /* @__PURE__ */ zod.object({
    format: zod.enum(['csv', 'json']).optional(),
})

export const ActionsPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this action.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionsPartialUpdateQueryParams = /* @__PURE__ */ zod.object({
    format: zod.enum(['csv', 'json']).optional(),
})

export const actionsPartialUpdateBodyNameMax = 400

export const actionsPartialUpdateBodySlackMessageFormatMax = 1200

export const ActionsPartialUpdateBody = /* @__PURE__ */ zod
    .object({
        name: zod.string().max(actionsPartialUpdateBodyNameMax).nullish(),
        description: zod.string().optional(),
        tags: zod.array(zod.unknown()).optional(),
        post_to_slack: zod.boolean().optional(),
        slack_message_format: zod.string().max(actionsPartialUpdateBodySlackMessageFormatMax).optional(),
        steps: zod
            .array(
                zod.object({
                    event: zod.string().nullish(),
                    properties: zod.array(zod.record(zod.string(), zod.unknown())).nullish(),
                    selector: zod.string().nullish(),
                    selector_regex: zod.string().nullish(),
                    tag_name: zod.string().nullish(),
                    text: zod.string().nullish(),
                    text_matching: zod
                        .union([
                            zod
                                .enum(['contains', 'regex', 'exact'])
                                .describe('* `contains` - contains\n* `regex` - regex\n* `exact` - exact'),
                            zod.literal(null),
                        ])
                        .nullish(),
                    href: zod.string().nullish(),
                    href_matching: zod
                        .union([
                            zod
                                .enum(['contains', 'regex', 'exact'])
                                .describe('* `contains` - contains\n* `regex` - regex\n* `exact` - exact'),
                            zod.literal(null),
                        ])
                        .nullish(),
                    url: zod.string().nullish(),
                    url_matching: zod
                        .union([
                            zod
                                .enum(['contains', 'regex', 'exact'])
                                .describe('* `contains` - contains\n* `regex` - regex\n* `exact` - exact'),
                            zod.literal(null),
                        ])
                        .nullish(),
                })
            )
            .optional(),
        pinned_at: zod.iso.datetime({}).nullish(),
        _create_in_folder: zod.string().optional(),
    })
    .describe('Serializer mixin that handles tags for objects.')

/**
 * Hard delete of this model is not allowed. Use a patch API call to set "deleted" to true
 */
export const ActionsDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this action.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ActionsDestroyQueryParams = /* @__PURE__ */ zod.object({
    format: zod.enum(['csv', 'json']).optional(),
})
