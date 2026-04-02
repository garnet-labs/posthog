/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 16 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const FeatureFlagsCopyFlagsCreateParams = /* @__PURE__ */ zod.object({
    organization_id: zod.string(),
})

/**
 * Create, read, update and delete feature flags. [See docs](https://posthog.com/docs/feature-flags) for more information on feature flags.

If you're looking to use feature flags on your application, you can either use our JavaScript Library or our dedicated endpoint to check if feature flags are enabled for a given user.
 */
export const FeatureFlagsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const FeatureFlagsListQueryParams = /* @__PURE__ */ zod.object({
    active: zod.enum(['STALE', 'false', 'true']).optional(),
    created_by_id: zod.string().optional().describe('The User ID which initially created the feature flag.'),
    evaluation_runtime: zod
        .enum(['both', 'client', 'server'])
        .optional()
        .describe('Filter feature flags by their evaluation runtime.'),
    excluded_properties: zod
        .string()
        .optional()
        .describe('JSON-encoded list of feature flag keys to exclude from the results.'),
    has_evaluation_tags: zod
        .enum(['false', 'true'])
        .optional()
        .describe(
            "Filter feature flags by presence of evaluation context tags. 'true' returns only flags with at least one evaluation tag, 'false' returns only flags without evaluation tags."
        ),
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
    search: zod.string().optional().describe('Search by feature flag key or name. Case insensitive.'),
    tags: zod.string().optional().describe('JSON-encoded list of tag names to filter feature flags by.'),
    type: zod.enum(['boolean', 'experiment', 'multivariant']).optional(),
})

/**
 * Create, read, update and delete feature flags. [See docs](https://posthog.com/docs/feature-flags) for more information on feature flags.

If you're looking to use feature flags on your application, you can either use our JavaScript Library or our dedicated endpoint to check if feature flags are enabled for a given user.
 */
export const FeatureFlagsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const featureFlagsCreateBodyKeyMax = 400

export const featureFlagsCreateBodyVersionDefault = 0
export const featureFlagsCreateBodyShouldCreateUsageDashboardDefault = true

export const FeatureFlagsCreateBody = /* @__PURE__ */ zod
    .object({
        name: zod
            .string()
            .optional()
            .describe('contains the description for the flag (field name `name` is kept for backwards-compatibility)'),
        key: zod.string().max(featureFlagsCreateBodyKeyMax),
        filters: zod.record(zod.string(), zod.unknown()).optional(),
        deleted: zod.boolean().optional(),
        active: zod.boolean().optional(),
        created_at: zod.iso.datetime({}).optional(),
        version: zod.number().default(featureFlagsCreateBodyVersionDefault),
        ensure_experience_continuity: zod.boolean().nullish(),
        rollback_conditions: zod.unknown().nullish(),
        performed_rollback: zod.boolean().nullish(),
        tags: zod.array(zod.unknown()).optional(),
        evaluation_tags: zod.array(zod.unknown()).optional(),
        analytics_dashboards: zod.array(zod.number()).optional(),
        has_enriched_analytics: zod.boolean().nullish(),
        creation_context: zod
            .enum([
                'feature_flags',
                'experiments',
                'surveys',
                'early_access_features',
                'web_experiments',
                'product_tours',
            ])
            .describe(
                '* `feature_flags` - feature_flags\n* `experiments` - experiments\n* `surveys` - surveys\n* `early_access_features` - early_access_features\n* `web_experiments` - web_experiments\n* `product_tours` - product_tours'
            )
            .optional()
            .describe(
                "Indicates the origin product of the feature flag. Choices: 'feature_flags', 'experiments', 'surveys', 'early_access_features', 'web_experiments', 'product_tours'.\n\n* `feature_flags` - feature_flags\n* `experiments` - experiments\n* `surveys` - surveys\n* `early_access_features` - early_access_features\n* `web_experiments` - web_experiments\n* `product_tours` - product_tours"
            ),
        is_remote_configuration: zod.boolean().nullish(),
        has_encrypted_payloads: zod.boolean().nullish(),
        evaluation_runtime: zod
            .union([
                zod
                    .enum(['server', 'client', 'all'])
                    .describe('* `server` - Server\n* `client` - Client\n* `all` - All'),
                zod.enum(['']),
                zod.literal(null),
            ])
            .nullish()
            .describe(
                'Specifies where this feature flag should be evaluated\n\n* `server` - Server\n* `client` - Client\n* `all` - All'
            ),
        bucketing_identifier: zod
            .union([
                zod
                    .enum(['distinct_id', 'device_id'])
                    .describe('* `distinct_id` - User ID (default)\n* `device_id` - Device ID'),
                zod.enum(['']),
                zod.literal(null),
            ])
            .nullish()
            .describe(
                'Identifier used for bucketing users into rollout and variants\n\n* `distinct_id` - User ID (default)\n* `device_id` - Device ID'
            ),
        last_called_at: zod.iso
            .datetime({})
            .nullish()
            .describe('Last time this feature flag was called (from $feature_flag_called events)'),
        _create_in_folder: zod.string().optional(),
        _should_create_usage_dashboard: zod.boolean().default(featureFlagsCreateBodyShouldCreateUsageDashboardDefault),
    })
    .describe('Serializer mixin that handles tags for objects.')

/**
 * Create, read, update and delete feature flags. [See docs](https://posthog.com/docs/feature-flags) for more information on feature flags.

If you're looking to use feature flags on your application, you can either use our JavaScript Library or our dedicated endpoint to check if feature flags are enabled for a given user.
 */
export const FeatureFlagsRetrieve2Params = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this feature flag.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

/**
 * Create, read, update and delete feature flags. [See docs](https://posthog.com/docs/feature-flags) for more information on feature flags.

If you're looking to use feature flags on your application, you can either use our JavaScript Library or our dedicated endpoint to check if feature flags are enabled for a given user.
 */
export const FeatureFlagsPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this feature flag.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const featureFlagsPartialUpdateBodyKeyMax = 400

export const featureFlagsPartialUpdateBodyVersionDefault = 0
export const featureFlagsPartialUpdateBodyShouldCreateUsageDashboardDefault = true

export const FeatureFlagsPartialUpdateBody = /* @__PURE__ */ zod
    .object({
        name: zod
            .string()
            .optional()
            .describe('contains the description for the flag (field name `name` is kept for backwards-compatibility)'),
        key: zod.string().max(featureFlagsPartialUpdateBodyKeyMax).optional(),
        filters: zod.record(zod.string(), zod.unknown()).optional(),
        deleted: zod.boolean().optional(),
        active: zod.boolean().optional(),
        created_at: zod.iso.datetime({}).optional(),
        version: zod.number().default(featureFlagsPartialUpdateBodyVersionDefault),
        ensure_experience_continuity: zod.boolean().nullish(),
        rollback_conditions: zod.unknown().nullish(),
        performed_rollback: zod.boolean().nullish(),
        tags: zod.array(zod.unknown()).optional(),
        evaluation_tags: zod.array(zod.unknown()).optional(),
        analytics_dashboards: zod.array(zod.number()).optional(),
        has_enriched_analytics: zod.boolean().nullish(),
        creation_context: zod
            .enum([
                'feature_flags',
                'experiments',
                'surveys',
                'early_access_features',
                'web_experiments',
                'product_tours',
            ])
            .describe(
                '* `feature_flags` - feature_flags\n* `experiments` - experiments\n* `surveys` - surveys\n* `early_access_features` - early_access_features\n* `web_experiments` - web_experiments\n* `product_tours` - product_tours'
            )
            .optional()
            .describe(
                "Indicates the origin product of the feature flag. Choices: 'feature_flags', 'experiments', 'surveys', 'early_access_features', 'web_experiments', 'product_tours'.\n\n* `feature_flags` - feature_flags\n* `experiments` - experiments\n* `surveys` - surveys\n* `early_access_features` - early_access_features\n* `web_experiments` - web_experiments\n* `product_tours` - product_tours"
            ),
        is_remote_configuration: zod.boolean().nullish(),
        has_encrypted_payloads: zod.boolean().nullish(),
        evaluation_runtime: zod
            .union([
                zod
                    .enum(['server', 'client', 'all'])
                    .describe('* `server` - Server\n* `client` - Client\n* `all` - All'),
                zod.enum(['']),
                zod.literal(null),
            ])
            .nullish()
            .describe(
                'Specifies where this feature flag should be evaluated\n\n* `server` - Server\n* `client` - Client\n* `all` - All'
            ),
        bucketing_identifier: zod
            .union([
                zod
                    .enum(['distinct_id', 'device_id'])
                    .describe('* `distinct_id` - User ID (default)\n* `device_id` - Device ID'),
                zod.enum(['']),
                zod.literal(null),
            ])
            .nullish()
            .describe(
                'Identifier used for bucketing users into rollout and variants\n\n* `distinct_id` - User ID (default)\n* `device_id` - Device ID'
            ),
        last_called_at: zod.iso
            .datetime({})
            .nullish()
            .describe('Last time this feature flag was called (from $feature_flag_called events)'),
        _create_in_folder: zod.string().optional(),
        _should_create_usage_dashboard: zod
            .boolean()
            .default(featureFlagsPartialUpdateBodyShouldCreateUsageDashboardDefault),
    })
    .describe('Serializer mixin that handles tags for objects.')

/**
 * Hard delete of this model is not allowed. Use a patch API call to set "deleted" to true
 */
export const FeatureFlagsDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this feature flag.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

/**
 * Create, read, update and delete feature flags. [See docs](https://posthog.com/docs/feature-flags) for more information on feature flags.

If you're looking to use feature flags on your application, you can either use our JavaScript Library or our dedicated endpoint to check if feature flags are enabled for a given user.
 */
export const FeatureFlagsActivityRetrieve2Params = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this feature flag.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const featureFlagsActivityRetrieve2QueryLimitDefault = 10

export const featureFlagsActivityRetrieve2QueryPageDefault = 1

export const FeatureFlagsActivityRetrieve2QueryParams = /* @__PURE__ */ zod.object({
    limit: zod
        .number()
        .min(1)
        .default(featureFlagsActivityRetrieve2QueryLimitDefault)
        .describe('Number of items per page'),
    page: zod.number().min(1).default(featureFlagsActivityRetrieve2QueryPageDefault).describe('Page number'),
})

/**
 * Create, read, update and delete feature flags. [See docs](https://posthog.com/docs/feature-flags) for more information on feature flags.

If you're looking to use feature flags on your application, you can either use our JavaScript Library or our dedicated endpoint to check if feature flags are enabled for a given user.
 */
export const FeatureFlagsStatusRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this feature flag.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

/**
 * Create, read, update and delete feature flags. [See docs](https://posthog.com/docs/feature-flags) for more information on feature flags.

If you're looking to use feature flags on your application, you can either use our JavaScript Library or our dedicated endpoint to check if feature flags are enabled for a given user.
 */
export const FeatureFlagsEvaluationReasonsRetrieveParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const featureFlagsEvaluationReasonsRetrieveQueryGroupsDefault = `{}`

export const FeatureFlagsEvaluationReasonsRetrieveQueryParams = /* @__PURE__ */ zod.object({
    distinct_id: zod.string().min(1).describe('User distinct ID'),
    groups: zod
        .string()
        .default(featureFlagsEvaluationReasonsRetrieveQueryGroupsDefault)
        .describe('Groups for feature flag evaluation (JSON object string)'),
})

/**
 * Create, read, update and delete feature flags. [See docs](https://posthog.com/docs/feature-flags) for more information on feature flags.

If you're looking to use feature flags on your application, you can either use our JavaScript Library or our dedicated endpoint to check if feature flags are enabled for a given user.
 */
export const FeatureFlagsUserBlastRadiusCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const featureFlagsUserBlastRadiusCreateBodyKeyMax = 400

export const featureFlagsUserBlastRadiusCreateBodyVersionDefault = 0
export const featureFlagsUserBlastRadiusCreateBodyShouldCreateUsageDashboardDefault = true

export const FeatureFlagsUserBlastRadiusCreateBody = /* @__PURE__ */ zod
    .object({
        name: zod
            .string()
            .optional()
            .describe('contains the description for the flag (field name `name` is kept for backwards-compatibility)'),
        key: zod.string().max(featureFlagsUserBlastRadiusCreateBodyKeyMax),
        filters: zod.record(zod.string(), zod.unknown()).optional(),
        deleted: zod.boolean().optional(),
        active: zod.boolean().optional(),
        created_at: zod.iso.datetime({}).optional(),
        version: zod.number().default(featureFlagsUserBlastRadiusCreateBodyVersionDefault),
        ensure_experience_continuity: zod.boolean().nullish(),
        rollback_conditions: zod.unknown().nullish(),
        performed_rollback: zod.boolean().nullish(),
        tags: zod.array(zod.unknown()).optional(),
        evaluation_tags: zod.array(zod.unknown()).optional(),
        analytics_dashboards: zod.array(zod.number()).optional(),
        has_enriched_analytics: zod.boolean().nullish(),
        creation_context: zod
            .enum([
                'feature_flags',
                'experiments',
                'surveys',
                'early_access_features',
                'web_experiments',
                'product_tours',
            ])
            .describe(
                '* `feature_flags` - feature_flags\n* `experiments` - experiments\n* `surveys` - surveys\n* `early_access_features` - early_access_features\n* `web_experiments` - web_experiments\n* `product_tours` - product_tours'
            )
            .optional()
            .describe(
                "Indicates the origin product of the feature flag. Choices: 'feature_flags', 'experiments', 'surveys', 'early_access_features', 'web_experiments', 'product_tours'.\n\n* `feature_flags` - feature_flags\n* `experiments` - experiments\n* `surveys` - surveys\n* `early_access_features` - early_access_features\n* `web_experiments` - web_experiments\n* `product_tours` - product_tours"
            ),
        is_remote_configuration: zod.boolean().nullish(),
        has_encrypted_payloads: zod.boolean().nullish(),
        evaluation_runtime: zod
            .union([
                zod
                    .enum(['server', 'client', 'all'])
                    .describe('* `server` - Server\n* `client` - Client\n* `all` - All'),
                zod.enum(['']),
                zod.literal(null),
            ])
            .nullish()
            .describe(
                'Specifies where this feature flag should be evaluated\n\n* `server` - Server\n* `client` - Client\n* `all` - All'
            ),
        bucketing_identifier: zod
            .union([
                zod
                    .enum(['distinct_id', 'device_id'])
                    .describe('* `distinct_id` - User ID (default)\n* `device_id` - Device ID'),
                zod.enum(['']),
                zod.literal(null),
            ])
            .nullish()
            .describe(
                'Identifier used for bucketing users into rollout and variants\n\n* `distinct_id` - User ID (default)\n* `device_id` - Device ID'
            ),
        last_called_at: zod.iso
            .datetime({})
            .nullish()
            .describe('Last time this feature flag was called (from $feature_flag_called events)'),
        _create_in_folder: zod.string().optional(),
        _should_create_usage_dashboard: zod
            .boolean()
            .default(featureFlagsUserBlastRadiusCreateBodyShouldCreateUsageDashboardDefault),
    })
    .describe('Serializer mixin that handles tags for objects.')

/**
 * Create, read, update and delete scheduled changes.
 */
export const ScheduledChangesListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const ScheduledChangesListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

/**
 * Create, read, update and delete scheduled changes.
 */
export const ScheduledChangesCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const scheduledChangesCreateBodyRecordIdMax = 200

export const ScheduledChangesCreateBody = /* @__PURE__ */ zod.object({
    record_id: zod.string().max(scheduledChangesCreateBodyRecordIdMax),
    model_name: zod.enum(['FeatureFlag']).describe('* `FeatureFlag` - feature flag'),
    payload: zod.unknown().optional(),
    scheduled_at: zod.iso.datetime({}),
    is_recurring: zod.boolean().optional(),
    recurrence_interval: zod
        .union([
            zod
                .enum(['daily', 'weekly', 'monthly', 'yearly'])
                .describe('* `daily` - daily\n* `weekly` - weekly\n* `monthly` - monthly\n* `yearly` - yearly'),
            zod.enum(['']),
            zod.literal(null),
        ])
        .nullish(),
    end_date: zod.iso.datetime({}).nullish(),
})

/**
 * Create, read, update and delete scheduled changes.
 */
export const ScheduledChangesRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this scheduled change.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

/**
 * Create, read, update and delete scheduled changes.
 */
export const ScheduledChangesPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this scheduled change.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const scheduledChangesPartialUpdateBodyRecordIdMax = 200

export const ScheduledChangesPartialUpdateBody = /* @__PURE__ */ zod.object({
    record_id: zod.string().max(scheduledChangesPartialUpdateBodyRecordIdMax).optional(),
    model_name: zod.enum(['FeatureFlag']).optional().describe('* `FeatureFlag` - feature flag'),
    payload: zod.unknown().optional(),
    scheduled_at: zod.iso.datetime({}).optional(),
    is_recurring: zod.boolean().optional(),
    recurrence_interval: zod
        .union([
            zod
                .enum(['daily', 'weekly', 'monthly', 'yearly'])
                .describe('* `daily` - daily\n* `weekly` - weekly\n* `monthly` - monthly\n* `yearly` - yearly'),
            zod.enum(['']),
            zod.literal(null),
        ])
        .nullish(),
    end_date: zod.iso.datetime({}).nullish(),
})

/**
 * Create, read, update and delete scheduled changes.
 */
export const ScheduledChangesDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this scheduled change.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})
