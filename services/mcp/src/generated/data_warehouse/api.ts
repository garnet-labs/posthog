/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 9 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

/**
 * Create, Read, Update and Delete Warehouse Tables.
 */
export const WarehouseSavedQueriesListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const WarehouseSavedQueriesListQueryParams = /* @__PURE__ */ zod.object({
    page: zod.number().optional().describe('A page number within the paginated result set.'),
    search: zod.string().optional().describe('A search term.'),
})

/**
 * Create, Read, Update and Delete Warehouse Tables.
 */
export const WarehouseSavedQueriesCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const warehouseSavedQueriesCreateBodyNameMax = 128

export const WarehouseSavedQueriesCreateBody = /* @__PURE__ */ zod
    .object({
        name: zod.string().max(warehouseSavedQueriesCreateBodyNameMax),
        query: zod.unknown().nullish().describe('HogQL query'),
    })
    .describe(
        'Shared methods for DataWarehouseSavedQuery serializers.\n\nThis mixin is intended to be used with serializers.ModelSerializer subclasses.'
    )

/**
 * Create, Read, Update and Delete Warehouse Tables.
 */
export const WarehouseSavedQueriesRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this data warehouse saved query.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

/**
 * Create, Read, Update and Delete Warehouse Tables.
 */
export const WarehouseSavedQueriesPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this data warehouse saved query.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const warehouseSavedQueriesPartialUpdateBodyNameMax = 128

export const WarehouseSavedQueriesPartialUpdateBody = /* @__PURE__ */ zod
    .object({
        name: zod.string().max(warehouseSavedQueriesPartialUpdateBodyNameMax).optional(),
        query: zod.unknown().nullish().describe('HogQL query'),
        edited_history_id: zod.string().nullish(),
    })
    .describe(
        'Shared methods for DataWarehouseSavedQuery serializers.\n\nThis mixin is intended to be used with serializers.ModelSerializer subclasses.'
    )

/**
 * Create, Read, Update and Delete Warehouse Tables.
 */
export const WarehouseSavedQueriesDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this data warehouse saved query.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

/**
 * Enable materialization for this saved query with a 24-hour sync frequency.
 */
export const WarehouseSavedQueriesMaterializeCreateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this data warehouse saved query.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const warehouseSavedQueriesMaterializeCreateBodyNameMax = 128

export const WarehouseSavedQueriesMaterializeCreateBody = /* @__PURE__ */ zod
    .object({
        deleted: zod.boolean().nullish(),
        name: zod.string().max(warehouseSavedQueriesMaterializeCreateBodyNameMax),
        query: zod.unknown().nullish().describe('HogQL query'),
        edited_history_id: zod.string().nullish(),
        soft_update: zod.boolean().nullish(),
    })
    .describe(
        'Shared methods for DataWarehouseSavedQuery serializers.\n\nThis mixin is intended to be used with serializers.ModelSerializer subclasses.'
    )

/**
 * Undo materialization, revert back to the original view.
(i.e. delete the materialized table and the schedule)
 */
export const WarehouseSavedQueriesRevertMaterializationCreateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this data warehouse saved query.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const warehouseSavedQueriesRevertMaterializationCreateBodyNameMax = 128

export const WarehouseSavedQueriesRevertMaterializationCreateBody = /* @__PURE__ */ zod
    .object({
        deleted: zod.boolean().nullish(),
        name: zod.string().max(warehouseSavedQueriesRevertMaterializationCreateBodyNameMax),
        query: zod.unknown().nullish().describe('HogQL query'),
        edited_history_id: zod.string().nullish(),
        soft_update: zod.boolean().nullish(),
    })
    .describe(
        'Shared methods for DataWarehouseSavedQuery serializers.\n\nThis mixin is intended to be used with serializers.ModelSerializer subclasses.'
    )

/**
 * Run this saved query.
 */
export const WarehouseSavedQueriesRunCreateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this data warehouse saved query.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const warehouseSavedQueriesRunCreateBodyNameMax = 128

export const WarehouseSavedQueriesRunCreateBody = /* @__PURE__ */ zod
    .object({
        deleted: zod.boolean().nullish(),
        name: zod.string().max(warehouseSavedQueriesRunCreateBodyNameMax),
        query: zod.unknown().nullish().describe('HogQL query'),
        edited_history_id: zod.string().nullish(),
        soft_update: zod.boolean().nullish(),
    })
    .describe(
        'Shared methods for DataWarehouseSavedQuery serializers.\n\nThis mixin is intended to be used with serializers.ModelSerializer subclasses.'
    )

/**
 * Return the recent run history (up to 5 most recent) for this materialized view.
 */
export const WarehouseSavedQueriesRunHistoryRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this data warehouse saved query.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})
