/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 6 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const CohortsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const CohortsListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

export const CohortsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const cohortsCreateBodyNameMax = 400

export const cohortsCreateBodyDescriptionMax = 1000

export const CohortsCreateBody = /* @__PURE__ */ zod.object({
    name: zod.string().max(cohortsCreateBodyNameMax).nullish(),
    description: zod.string().max(cohortsCreateBodyDescriptionMax).optional(),
    filters: zod
        .unknown()
        .nullish()
        .describe(
            'Filters for the cohort. Examples:\n\n        # Behavioral filter (performed event)\n        {\n            "properties": {\n                "type": "OR",\n                "values": [{\n                    "type": "OR",\n                    "values": [{\n                        "key": "address page viewed",\n                        "type": "behavioral",\n                        "value": "performed_event",\n                        "negation": false,\n                        "event_type": "events",\n                        "time_value": "30",\n                        "time_interval": "day"\n                    }]\n                }]\n            }\n        }\n\n        # Person property filter\n        {\n            "properties": {\n                "type": "OR",\n                "values": [{\n                    "type": "AND",\n                    "values": [{\n                        "key": "promoCodes",\n                        "type": "person",\n                        "value": ["1234567890"],\n                        "negation": false,\n                        "operator": "exact"\n                    }]\n                }]\n            }\n        }\n\n        # Cohort filter\n        {\n            "properties": {\n                "type": "OR",\n                "values": [{\n                    "type": "AND",\n                    "values": [{\n                        "key": "id",\n                        "type": "cohort",\n                        "value": 8814,\n                        "negation": false\n                    }]\n                }]\n            }\n        }'
        ),
    query: zod.unknown().nullish(),
    is_static: zod.boolean().optional(),
    cohort_type: zod
        .union([
            zod
                .enum(['static', 'person_property', 'behavioral', 'realtime', 'analytical'])
                .describe(
                    '* `static` - static\n* `person_property` - person_property\n* `behavioral` - behavioral\n* `realtime` - realtime\n* `analytical` - analytical'
                ),
            zod.enum(['']),
            zod.literal(null),
        ])
        .nullish()
        .describe(
            'Type of cohort based on filter complexity\n\n* `static` - static\n* `person_property` - person_property\n* `behavioral` - behavioral\n* `realtime` - realtime\n* `analytical` - analytical'
        ),
    _create_in_folder: zod.string().optional(),
    _create_static_person_ids: zod.array(zod.string()).optional(),
})

export const CohortsRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this cohort.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const CohortsPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this cohort.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const cohortsPartialUpdateBodyNameMax = 400

export const cohortsPartialUpdateBodyDescriptionMax = 1000

export const CohortsPartialUpdateBody = /* @__PURE__ */ zod.object({
    name: zod.string().max(cohortsPartialUpdateBodyNameMax).nullish(),
    description: zod.string().max(cohortsPartialUpdateBodyDescriptionMax).optional(),
    deleted: zod.boolean().optional(),
    filters: zod
        .unknown()
        .nullish()
        .describe(
            'Filters for the cohort. Examples:\n\n        # Behavioral filter (performed event)\n        {\n            "properties": {\n                "type": "OR",\n                "values": [{\n                    "type": "OR",\n                    "values": [{\n                        "key": "address page viewed",\n                        "type": "behavioral",\n                        "value": "performed_event",\n                        "negation": false,\n                        "event_type": "events",\n                        "time_value": "30",\n                        "time_interval": "day"\n                    }]\n                }]\n            }\n        }\n\n        # Person property filter\n        {\n            "properties": {\n                "type": "OR",\n                "values": [{\n                    "type": "AND",\n                    "values": [{\n                        "key": "promoCodes",\n                        "type": "person",\n                        "value": ["1234567890"],\n                        "negation": false,\n                        "operator": "exact"\n                    }]\n                }]\n            }\n        }\n\n        # Cohort filter\n        {\n            "properties": {\n                "type": "OR",\n                "values": [{\n                    "type": "AND",\n                    "values": [{\n                        "key": "id",\n                        "type": "cohort",\n                        "value": 8814,\n                        "negation": false\n                    }]\n                }]\n            }\n        }'
        ),
    query: zod.unknown().nullish(),
    is_static: zod.boolean().optional(),
    cohort_type: zod
        .union([
            zod
                .enum(['static', 'person_property', 'behavioral', 'realtime', 'analytical'])
                .describe(
                    '* `static` - static\n* `person_property` - person_property\n* `behavioral` - behavioral\n* `realtime` - realtime\n* `analytical` - analytical'
                ),
            zod.enum(['']),
            zod.literal(null),
        ])
        .nullish()
        .describe(
            'Type of cohort based on filter complexity\n\n* `static` - static\n* `person_property` - person_property\n* `behavioral` - behavioral\n* `realtime` - realtime\n* `analytical` - analytical'
        ),
    _create_in_folder: zod.string().optional(),
    _create_static_person_ids: zod.array(zod.string()).optional(),
})

export const CohortsAddPersonsToStaticCohortPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this cohort.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const CohortsAddPersonsToStaticCohortPartialUpdateBody = /* @__PURE__ */ zod.object({
    person_ids: zod.array(zod.string()).optional().describe('List of person UUIDs to add to the cohort'),
})

export const CohortsRemovePersonFromStaticCohortPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.number().describe('A unique integer value identifying this cohort.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const CohortsRemovePersonFromStaticCohortPartialUpdateBody = /* @__PURE__ */ zod.object({
    person_id: zod.string().optional().describe('Person UUID to remove from the cohort'),
})
