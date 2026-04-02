/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 6 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const AlertsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const AlertsListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

export const AlertsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const alertsCreateBodyNameMax = 255

export const alertsCreateBodyThresholdNameMax = 255

export const alertsCreateBodyConfigOneTypeDefault = `TrendsAlertConfig`

export const AlertsCreateBody = /* @__PURE__ */ zod.object({
    insight: zod
        .number()
        .describe('Insight ID monitored by this alert. Note: Response returns full InsightBasicSerializer object.'),
    name: zod.string().max(alertsCreateBodyNameMax).optional(),
    subscribed_users: zod
        .array(zod.number())
        .describe('User IDs to subscribe to this alert. Note: Response returns full UserBasicSerializer object.'),
    threshold: zod.object({
        id: zod.string().optional(),
        created_at: zod.iso.datetime({}).optional(),
        name: zod.string().max(alertsCreateBodyThresholdNameMax).optional(),
        configuration: zod.object({
            bounds: zod
                .object({
                    lower: zod.number().nullish(),
                    upper: zod.number().nullish(),
                })
                .nullish(),
            type: zod.enum(['absolute', 'percentage']),
        }),
    }),
    condition: zod
        .object({
            type: zod.enum(['absolute_value', 'relative_increase', 'relative_decrease']),
        })
        .nullish(),
    enabled: zod.boolean().optional(),
    config: zod
        .object({
            check_ongoing_interval: zod.boolean().nullish(),
            series_index: zod.number(),
            type: zod.enum(['TrendsAlertConfig']).default(alertsCreateBodyConfigOneTypeDefault),
        })
        .nullish(),
    calculation_interval: zod
        .union([
            zod
                .enum(['hourly', 'daily', 'weekly', 'monthly'])
                .describe('* `hourly` - hourly\n* `daily` - daily\n* `weekly` - weekly\n* `monthly` - monthly'),
            zod.enum(['']),
            zod.literal(null),
        ])
        .nullish(),
    snoozed_until: zod.iso.datetime({}).nullish(),
    skip_weekend: zod.boolean().nullish(),
})

export const AlertsRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this alert configuration.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const AlertsPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this alert configuration.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const alertsPartialUpdateBodyNameMax = 255

export const alertsPartialUpdateBodyThresholdNameMax = 255

export const alertsPartialUpdateBodyConfigOneTypeDefault = `TrendsAlertConfig`

export const AlertsPartialUpdateBody = /* @__PURE__ */ zod.object({
    insight: zod
        .number()
        .optional()
        .describe('Insight ID monitored by this alert. Note: Response returns full InsightBasicSerializer object.'),
    name: zod.string().max(alertsPartialUpdateBodyNameMax).optional(),
    subscribed_users: zod
        .array(zod.number())
        .optional()
        .describe('User IDs to subscribe to this alert. Note: Response returns full UserBasicSerializer object.'),
    threshold: zod
        .object({
            id: zod.string().optional(),
            created_at: zod.iso.datetime({}).optional(),
            name: zod.string().max(alertsPartialUpdateBodyThresholdNameMax).optional(),
            configuration: zod.object({
                bounds: zod
                    .object({
                        lower: zod.number().nullish(),
                        upper: zod.number().nullish(),
                    })
                    .nullish(),
                type: zod.enum(['absolute', 'percentage']),
            }),
        })
        .optional(),
    condition: zod
        .object({
            type: zod.enum(['absolute_value', 'relative_increase', 'relative_decrease']),
        })
        .nullish(),
    enabled: zod.boolean().optional(),
    config: zod
        .object({
            check_ongoing_interval: zod.boolean().nullish(),
            series_index: zod.number(),
            type: zod.enum(['TrendsAlertConfig']).default(alertsPartialUpdateBodyConfigOneTypeDefault),
        })
        .nullish(),
    calculation_interval: zod
        .union([
            zod
                .enum(['hourly', 'daily', 'weekly', 'monthly'])
                .describe('* `hourly` - hourly\n* `daily` - daily\n* `weekly` - weekly\n* `monthly` - monthly'),
            zod.enum(['']),
            zod.literal(null),
        ])
        .nullish(),
    snoozed_until: zod.iso.datetime({}).nullish(),
    skip_weekend: zod.boolean().nullish(),
})

export const AlertsDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this alert configuration.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})
