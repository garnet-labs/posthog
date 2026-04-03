/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 7 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const HogFunctionsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const HogFunctionsListQueryParams = /* @__PURE__ */ zod.object({
    created_at: zod.iso.datetime({}).optional(),
    created_by: zod.number().optional(),
    enabled: zod.boolean().optional(),
    id: zod.string().optional(),
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
    search: zod.string().optional().describe('A search term.'),
    type: zod.array(zod.string()).optional().describe('Multiple values may be separated by commas.'),
    updated_at: zod.iso.datetime({}).optional(),
})

export const HogFunctionsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const hogFunctionsCreateBodyNameMax = 400

export const hogFunctionsCreateBodyInputsSchemaItemRequiredDefault = false
export const hogFunctionsCreateBodyInputsSchemaItemSecretDefault = false
export const hogFunctionsCreateBodyInputsSchemaItemHiddenDefault = false
export const hogFunctionsCreateBodyFiltersSourceDefault = `events`
export const hogFunctionsCreateBodyMaskingOneTtlMin = 60
export const hogFunctionsCreateBodyMaskingOneTtlMax = 86400

export const hogFunctionsCreateBodyMappingsItemInputsSchemaItemRequiredDefault = false
export const hogFunctionsCreateBodyMappingsItemInputsSchemaItemSecretDefault = false
export const hogFunctionsCreateBodyMappingsItemInputsSchemaItemHiddenDefault = false
export const hogFunctionsCreateBodyMappingsItemFiltersSourceDefault = `events`
export const hogFunctionsCreateBodyTemplateIdMax = 400

export const hogFunctionsCreateBodyExecutionOrderMin = 0
export const hogFunctionsCreateBodyExecutionOrderMax = 32767

export const HogFunctionsCreateBody = /* @__PURE__ */ zod.object({
    type: zod
        .union([
            zod
                .enum([
                    'destination',
                    'site_destination',
                    'internal_destination',
                    'source_webhook',
                    'warehouse_source_webhook',
                    'site_app',
                    'transformation',
                ])
                .describe(
                    '* `destination` - Destination\n* `site_destination` - Site Destination\n* `internal_destination` - Internal Destination\n* `source_webhook` - Source Webhook\n* `warehouse_source_webhook` - Warehouse Source Webhook\n* `site_app` - Site App\n* `transformation` - Transformation'
                ),
            zod.literal(null),
        ])
        .nullish(),
    name: zod.string().max(hogFunctionsCreateBodyNameMax).nullish(),
    description: zod.string().optional(),
    enabled: zod.boolean().optional(),
    hog: zod.string().optional(),
    inputs_schema: zod
        .array(
            zod.object({
                type: zod
                    .enum([
                        'string',
                        'number',
                        'boolean',
                        'dictionary',
                        'choice',
                        'json',
                        'integration',
                        'integration_field',
                        'email',
                        'native_email',
                    ])
                    .describe(
                        '* `string` - string\n* `number` - number\n* `boolean` - boolean\n* `dictionary` - dictionary\n* `choice` - choice\n* `json` - json\n* `integration` - integration\n* `integration_field` - integration_field\n* `email` - email\n* `native_email` - native_email'
                    ),
                key: zod.string(),
                label: zod.string().optional(),
                choices: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                required: zod.boolean().default(hogFunctionsCreateBodyInputsSchemaItemRequiredDefault),
                default: zod.unknown().optional(),
                secret: zod.boolean().default(hogFunctionsCreateBodyInputsSchemaItemSecretDefault),
                hidden: zod.boolean().default(hogFunctionsCreateBodyInputsSchemaItemHiddenDefault),
                description: zod.string().optional(),
                templating: zod
                    .union([zod.literal(true), zod.literal(false), zod.literal('hog'), zod.literal('liquid')])
                    .optional()
                    .describe('* `True` - True\n* `False` - False\n* `hog` - hog\n* `liquid` - liquid'),
            })
        )
        .optional(),
    inputs: zod
        .record(
            zod.string(),
            zod.object({
                value: zod.string().optional(),
                templating: zod.enum(['hog', 'liquid']).optional().describe('* `hog` - hog\n* `liquid` - liquid'),
                bytecode: zod.array(zod.unknown()).optional(),
                order: zod.number().optional(),
                transpiled: zod.unknown().optional(),
            })
        )
        .optional(),
    filters: zod
        .object({
            source: zod
                .enum(['events', 'person-updates', 'data-warehouse-table'])
                .describe(
                    '* `events` - events\n* `person-updates` - person-updates\n* `data-warehouse-table` - data-warehouse-table'
                )
                .default(hogFunctionsCreateBodyFiltersSourceDefault),
            actions: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            events: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            data_warehouse: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            properties: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            filter_test_accounts: zod.boolean().optional(),
        })
        .optional(),
    masking: zod
        .object({
            ttl: zod.number().min(hogFunctionsCreateBodyMaskingOneTtlMin).max(hogFunctionsCreateBodyMaskingOneTtlMax),
            threshold: zod.number().nullish(),
            hash: zod.string(),
            bytecode: zod.unknown().nullish(),
        })
        .nullish(),
    mappings: zod
        .array(
            zod.object({
                name: zod.string().optional(),
                inputs_schema: zod
                    .array(
                        zod.object({
                            type: zod
                                .enum([
                                    'string',
                                    'number',
                                    'boolean',
                                    'dictionary',
                                    'choice',
                                    'json',
                                    'integration',
                                    'integration_field',
                                    'email',
                                    'native_email',
                                ])
                                .describe(
                                    '* `string` - string\n* `number` - number\n* `boolean` - boolean\n* `dictionary` - dictionary\n* `choice` - choice\n* `json` - json\n* `integration` - integration\n* `integration_field` - integration_field\n* `email` - email\n* `native_email` - native_email'
                                ),
                            key: zod.string(),
                            label: zod.string().optional(),
                            choices: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                            required: zod
                                .boolean()
                                .default(hogFunctionsCreateBodyMappingsItemInputsSchemaItemRequiredDefault),
                            default: zod.unknown().optional(),
                            secret: zod
                                .boolean()
                                .default(hogFunctionsCreateBodyMappingsItemInputsSchemaItemSecretDefault),
                            hidden: zod
                                .boolean()
                                .default(hogFunctionsCreateBodyMappingsItemInputsSchemaItemHiddenDefault),
                            description: zod.string().optional(),
                            templating: zod
                                .union([
                                    zod.literal(true),
                                    zod.literal(false),
                                    zod.literal('hog'),
                                    zod.literal('liquid'),
                                ])
                                .optional()
                                .describe('* `True` - True\n* `False` - False\n* `hog` - hog\n* `liquid` - liquid'),
                        })
                    )
                    .optional(),
                inputs: zod
                    .record(
                        zod.string(),
                        zod.object({
                            value: zod.string().optional(),
                            templating: zod
                                .enum(['hog', 'liquid'])
                                .optional()
                                .describe('* `hog` - hog\n* `liquid` - liquid'),
                            bytecode: zod.array(zod.unknown()).optional(),
                            order: zod.number().optional(),
                            transpiled: zod.unknown().optional(),
                        })
                    )
                    .optional(),
                filters: zod
                    .object({
                        source: zod
                            .enum(['events', 'person-updates', 'data-warehouse-table'])
                            .describe(
                                '* `events` - events\n* `person-updates` - person-updates\n* `data-warehouse-table` - data-warehouse-table'
                            )
                            .default(hogFunctionsCreateBodyMappingsItemFiltersSourceDefault),
                        actions: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        events: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        data_warehouse: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        properties: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        filter_test_accounts: zod.boolean().optional(),
                    })
                    .optional(),
            })
        )
        .nullish(),
    icon_url: zod.string().nullish(),
    template_id: zod.string().max(hogFunctionsCreateBodyTemplateIdMax).nullish(),
    execution_order: zod
        .number()
        .min(hogFunctionsCreateBodyExecutionOrderMin)
        .max(hogFunctionsCreateBodyExecutionOrderMax)
        .nullish(),
})

export const HogFunctionsRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this hog function.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const HogFunctionsPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this hog function.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const hogFunctionsPartialUpdateBodyNameMax = 400

export const hogFunctionsPartialUpdateBodyInputsSchemaItemRequiredDefault = false
export const hogFunctionsPartialUpdateBodyInputsSchemaItemSecretDefault = false
export const hogFunctionsPartialUpdateBodyInputsSchemaItemHiddenDefault = false
export const hogFunctionsPartialUpdateBodyFiltersSourceDefault = `events`
export const hogFunctionsPartialUpdateBodyMaskingOneTtlMin = 60
export const hogFunctionsPartialUpdateBodyMaskingOneTtlMax = 86400

export const hogFunctionsPartialUpdateBodyMappingsItemInputsSchemaItemRequiredDefault = false
export const hogFunctionsPartialUpdateBodyMappingsItemInputsSchemaItemSecretDefault = false
export const hogFunctionsPartialUpdateBodyMappingsItemInputsSchemaItemHiddenDefault = false
export const hogFunctionsPartialUpdateBodyMappingsItemFiltersSourceDefault = `events`
export const hogFunctionsPartialUpdateBodyTemplateIdMax = 400

export const hogFunctionsPartialUpdateBodyExecutionOrderMin = 0
export const hogFunctionsPartialUpdateBodyExecutionOrderMax = 32767

export const HogFunctionsPartialUpdateBody = /* @__PURE__ */ zod.object({
    type: zod
        .union([
            zod
                .enum([
                    'destination',
                    'site_destination',
                    'internal_destination',
                    'source_webhook',
                    'warehouse_source_webhook',
                    'site_app',
                    'transformation',
                ])
                .describe(
                    '* `destination` - Destination\n* `site_destination` - Site Destination\n* `internal_destination` - Internal Destination\n* `source_webhook` - Source Webhook\n* `warehouse_source_webhook` - Warehouse Source Webhook\n* `site_app` - Site App\n* `transformation` - Transformation'
                ),
            zod.literal(null),
        ])
        .nullish(),
    name: zod.string().max(hogFunctionsPartialUpdateBodyNameMax).nullish(),
    description: zod.string().optional(),
    enabled: zod.boolean().optional(),
    hog: zod.string().optional(),
    inputs_schema: zod
        .array(
            zod.object({
                type: zod
                    .enum([
                        'string',
                        'number',
                        'boolean',
                        'dictionary',
                        'choice',
                        'json',
                        'integration',
                        'integration_field',
                        'email',
                        'native_email',
                    ])
                    .describe(
                        '* `string` - string\n* `number` - number\n* `boolean` - boolean\n* `dictionary` - dictionary\n* `choice` - choice\n* `json` - json\n* `integration` - integration\n* `integration_field` - integration_field\n* `email` - email\n* `native_email` - native_email'
                    ),
                key: zod.string(),
                label: zod.string().optional(),
                choices: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                required: zod.boolean().default(hogFunctionsPartialUpdateBodyInputsSchemaItemRequiredDefault),
                default: zod.unknown().optional(),
                secret: zod.boolean().default(hogFunctionsPartialUpdateBodyInputsSchemaItemSecretDefault),
                hidden: zod.boolean().default(hogFunctionsPartialUpdateBodyInputsSchemaItemHiddenDefault),
                description: zod.string().optional(),
                templating: zod
                    .union([zod.literal(true), zod.literal(false), zod.literal('hog'), zod.literal('liquid')])
                    .optional()
                    .describe('* `True` - True\n* `False` - False\n* `hog` - hog\n* `liquid` - liquid'),
            })
        )
        .optional(),
    inputs: zod
        .record(
            zod.string(),
            zod.object({
                value: zod.string().optional(),
                templating: zod.enum(['hog', 'liquid']).optional().describe('* `hog` - hog\n* `liquid` - liquid'),
                bytecode: zod.array(zod.unknown()).optional(),
                order: zod.number().optional(),
                transpiled: zod.unknown().optional(),
            })
        )
        .optional(),
    filters: zod
        .object({
            source: zod
                .enum(['events', 'person-updates', 'data-warehouse-table'])
                .describe(
                    '* `events` - events\n* `person-updates` - person-updates\n* `data-warehouse-table` - data-warehouse-table'
                )
                .default(hogFunctionsPartialUpdateBodyFiltersSourceDefault),
            actions: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            events: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            data_warehouse: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            properties: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            filter_test_accounts: zod.boolean().optional(),
        })
        .optional(),
    masking: zod
        .object({
            ttl: zod
                .number()
                .min(hogFunctionsPartialUpdateBodyMaskingOneTtlMin)
                .max(hogFunctionsPartialUpdateBodyMaskingOneTtlMax),
            threshold: zod.number().nullish(),
            hash: zod.string(),
            bytecode: zod.unknown().nullish(),
        })
        .nullish(),
    mappings: zod
        .array(
            zod.object({
                name: zod.string().optional(),
                inputs_schema: zod
                    .array(
                        zod.object({
                            type: zod
                                .enum([
                                    'string',
                                    'number',
                                    'boolean',
                                    'dictionary',
                                    'choice',
                                    'json',
                                    'integration',
                                    'integration_field',
                                    'email',
                                    'native_email',
                                ])
                                .describe(
                                    '* `string` - string\n* `number` - number\n* `boolean` - boolean\n* `dictionary` - dictionary\n* `choice` - choice\n* `json` - json\n* `integration` - integration\n* `integration_field` - integration_field\n* `email` - email\n* `native_email` - native_email'
                                ),
                            key: zod.string(),
                            label: zod.string().optional(),
                            choices: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                            required: zod
                                .boolean()
                                .default(hogFunctionsPartialUpdateBodyMappingsItemInputsSchemaItemRequiredDefault),
                            default: zod.unknown().optional(),
                            secret: zod
                                .boolean()
                                .default(hogFunctionsPartialUpdateBodyMappingsItemInputsSchemaItemSecretDefault),
                            hidden: zod
                                .boolean()
                                .default(hogFunctionsPartialUpdateBodyMappingsItemInputsSchemaItemHiddenDefault),
                            description: zod.string().optional(),
                            templating: zod
                                .union([
                                    zod.literal(true),
                                    zod.literal(false),
                                    zod.literal('hog'),
                                    zod.literal('liquid'),
                                ])
                                .optional()
                                .describe('* `True` - True\n* `False` - False\n* `hog` - hog\n* `liquid` - liquid'),
                        })
                    )
                    .optional(),
                inputs: zod
                    .record(
                        zod.string(),
                        zod.object({
                            value: zod.string().optional(),
                            templating: zod
                                .enum(['hog', 'liquid'])
                                .optional()
                                .describe('* `hog` - hog\n* `liquid` - liquid'),
                            bytecode: zod.array(zod.unknown()).optional(),
                            order: zod.number().optional(),
                            transpiled: zod.unknown().optional(),
                        })
                    )
                    .optional(),
                filters: zod
                    .object({
                        source: zod
                            .enum(['events', 'person-updates', 'data-warehouse-table'])
                            .describe(
                                '* `events` - events\n* `person-updates` - person-updates\n* `data-warehouse-table` - data-warehouse-table'
                            )
                            .default(hogFunctionsPartialUpdateBodyMappingsItemFiltersSourceDefault),
                        actions: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        events: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        data_warehouse: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        properties: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        filter_test_accounts: zod.boolean().optional(),
                    })
                    .optional(),
            })
        )
        .nullish(),
    icon_url: zod.string().nullish(),
    template_id: zod.string().max(hogFunctionsPartialUpdateBodyTemplateIdMax).nullish(),
    execution_order: zod
        .number()
        .min(hogFunctionsPartialUpdateBodyExecutionOrderMin)
        .max(hogFunctionsPartialUpdateBodyExecutionOrderMax)
        .nullish(),
})

/**
 * Hard delete of this model is not allowed. Use a patch API call to set "deleted" to true
 */
export const HogFunctionsDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this hog function.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const HogFunctionsInvocationsCreateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this hog function.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const hogFunctionsInvocationsCreateBodyNameMax = 400

export const hogFunctionsInvocationsCreateBodyInputsSchemaItemRequiredDefault = false
export const hogFunctionsInvocationsCreateBodyInputsSchemaItemSecretDefault = false
export const hogFunctionsInvocationsCreateBodyInputsSchemaItemHiddenDefault = false
export const hogFunctionsInvocationsCreateBodyFiltersSourceDefault = `events`
export const hogFunctionsInvocationsCreateBodyMaskingOneTtlMin = 60
export const hogFunctionsInvocationsCreateBodyMaskingOneTtlMax = 86400

export const hogFunctionsInvocationsCreateBodyMappingsItemInputsSchemaItemRequiredDefault = false
export const hogFunctionsInvocationsCreateBodyMappingsItemInputsSchemaItemSecretDefault = false
export const hogFunctionsInvocationsCreateBodyMappingsItemInputsSchemaItemHiddenDefault = false
export const hogFunctionsInvocationsCreateBodyMappingsItemFiltersSourceDefault = `events`
export const hogFunctionsInvocationsCreateBodyTemplateIdMax = 400

export const hogFunctionsInvocationsCreateBodyExecutionOrderMin = 0
export const hogFunctionsInvocationsCreateBodyExecutionOrderMax = 32767

export const HogFunctionsInvocationsCreateBody = /* @__PURE__ */ zod.object({
    type: zod
        .union([
            zod
                .enum([
                    'destination',
                    'site_destination',
                    'internal_destination',
                    'source_webhook',
                    'warehouse_source_webhook',
                    'site_app',
                    'transformation',
                ])
                .describe(
                    '* `destination` - Destination\n* `site_destination` - Site Destination\n* `internal_destination` - Internal Destination\n* `source_webhook` - Source Webhook\n* `warehouse_source_webhook` - Warehouse Source Webhook\n* `site_app` - Site App\n* `transformation` - Transformation'
                ),
            zod.literal(null),
        ])
        .nullish(),
    name: zod.string().max(hogFunctionsInvocationsCreateBodyNameMax).nullish(),
    description: zod.string().optional(),
    enabled: zod.boolean().optional(),
    deleted: zod.boolean().optional(),
    hog: zod.string().optional(),
    inputs_schema: zod
        .array(
            zod.object({
                type: zod
                    .enum([
                        'string',
                        'number',
                        'boolean',
                        'dictionary',
                        'choice',
                        'json',
                        'integration',
                        'integration_field',
                        'email',
                        'native_email',
                    ])
                    .describe(
                        '* `string` - string\n* `number` - number\n* `boolean` - boolean\n* `dictionary` - dictionary\n* `choice` - choice\n* `json` - json\n* `integration` - integration\n* `integration_field` - integration_field\n* `email` - email\n* `native_email` - native_email'
                    ),
                key: zod.string(),
                label: zod.string().optional(),
                choices: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                required: zod.boolean().default(hogFunctionsInvocationsCreateBodyInputsSchemaItemRequiredDefault),
                default: zod.unknown().optional(),
                secret: zod.boolean().default(hogFunctionsInvocationsCreateBodyInputsSchemaItemSecretDefault),
                hidden: zod.boolean().default(hogFunctionsInvocationsCreateBodyInputsSchemaItemHiddenDefault),
                description: zod.string().optional(),
                integration: zod.string().optional(),
                integration_key: zod.string().optional(),
                requires_field: zod.string().optional(),
                integration_field: zod.string().optional(),
                requiredScopes: zod.string().optional(),
                templating: zod
                    .union([zod.literal(true), zod.literal(false), zod.literal('hog'), zod.literal('liquid')])
                    .optional()
                    .describe('* `True` - True\n* `False` - False\n* `hog` - hog\n* `liquid` - liquid'),
            })
        )
        .optional(),
    inputs: zod
        .record(
            zod.string(),
            zod.object({
                value: zod.string().optional(),
                templating: zod.enum(['hog', 'liquid']).optional().describe('* `hog` - hog\n* `liquid` - liquid'),
                bytecode: zod.array(zod.unknown()).optional(),
                order: zod.number().optional(),
                transpiled: zod.unknown().optional(),
            })
        )
        .optional(),
    filters: zod
        .object({
            source: zod
                .enum(['events', 'person-updates', 'data-warehouse-table'])
                .describe(
                    '* `events` - events\n* `person-updates` - person-updates\n* `data-warehouse-table` - data-warehouse-table'
                )
                .default(hogFunctionsInvocationsCreateBodyFiltersSourceDefault),
            actions: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            events: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            data_warehouse: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            properties: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            bytecode: zod.unknown().nullish(),
            transpiled: zod.unknown().optional(),
            filter_test_accounts: zod.boolean().optional(),
            bytecode_error: zod.string().optional(),
        })
        .optional(),
    masking: zod
        .object({
            ttl: zod
                .number()
                .min(hogFunctionsInvocationsCreateBodyMaskingOneTtlMin)
                .max(hogFunctionsInvocationsCreateBodyMaskingOneTtlMax),
            threshold: zod.number().nullish(),
            hash: zod.string(),
            bytecode: zod.unknown().nullish(),
        })
        .nullish(),
    mappings: zod
        .array(
            zod.object({
                name: zod.string().optional(),
                inputs_schema: zod
                    .array(
                        zod.object({
                            type: zod
                                .enum([
                                    'string',
                                    'number',
                                    'boolean',
                                    'dictionary',
                                    'choice',
                                    'json',
                                    'integration',
                                    'integration_field',
                                    'email',
                                    'native_email',
                                ])
                                .describe(
                                    '* `string` - string\n* `number` - number\n* `boolean` - boolean\n* `dictionary` - dictionary\n* `choice` - choice\n* `json` - json\n* `integration` - integration\n* `integration_field` - integration_field\n* `email` - email\n* `native_email` - native_email'
                                ),
                            key: zod.string(),
                            label: zod.string().optional(),
                            choices: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                            required: zod
                                .boolean()
                                .default(hogFunctionsInvocationsCreateBodyMappingsItemInputsSchemaItemRequiredDefault),
                            default: zod.unknown().optional(),
                            secret: zod
                                .boolean()
                                .default(hogFunctionsInvocationsCreateBodyMappingsItemInputsSchemaItemSecretDefault),
                            hidden: zod
                                .boolean()
                                .default(hogFunctionsInvocationsCreateBodyMappingsItemInputsSchemaItemHiddenDefault),
                            description: zod.string().optional(),
                            integration: zod.string().optional(),
                            integration_key: zod.string().optional(),
                            requires_field: zod.string().optional(),
                            integration_field: zod.string().optional(),
                            requiredScopes: zod.string().optional(),
                            templating: zod
                                .union([
                                    zod.literal(true),
                                    zod.literal(false),
                                    zod.literal('hog'),
                                    zod.literal('liquid'),
                                ])
                                .optional()
                                .describe('* `True` - True\n* `False` - False\n* `hog` - hog\n* `liquid` - liquid'),
                        })
                    )
                    .optional(),
                inputs: zod
                    .record(
                        zod.string(),
                        zod.object({
                            value: zod.string().optional(),
                            templating: zod
                                .enum(['hog', 'liquid'])
                                .optional()
                                .describe('* `hog` - hog\n* `liquid` - liquid'),
                            bytecode: zod.array(zod.unknown()).optional(),
                            order: zod.number().optional(),
                            transpiled: zod.unknown().optional(),
                        })
                    )
                    .optional(),
                filters: zod
                    .object({
                        source: zod
                            .enum(['events', 'person-updates', 'data-warehouse-table'])
                            .describe(
                                '* `events` - events\n* `person-updates` - person-updates\n* `data-warehouse-table` - data-warehouse-table'
                            )
                            .default(hogFunctionsInvocationsCreateBodyMappingsItemFiltersSourceDefault),
                        actions: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        events: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        data_warehouse: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        properties: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        bytecode: zod.unknown().nullish(),
                        transpiled: zod.unknown().optional(),
                        filter_test_accounts: zod.boolean().optional(),
                        bytecode_error: zod.string().optional(),
                    })
                    .optional(),
            })
        )
        .nullish(),
    icon_url: zod.string().nullish(),
    template_id: zod.string().max(hogFunctionsInvocationsCreateBodyTemplateIdMax).nullish(),
    execution_order: zod
        .number()
        .min(hogFunctionsInvocationsCreateBodyExecutionOrderMin)
        .max(hogFunctionsInvocationsCreateBodyExecutionOrderMax)
        .nullish(),
    _create_in_folder: zod.string().optional(),
})

/**
 * Update the execution order of multiple HogFunctions.
 */
export const HogFunctionsRearrangePartialUpdateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const hogFunctionsRearrangePartialUpdateBodyNameMax = 400

export const hogFunctionsRearrangePartialUpdateBodyInputsSchemaItemRequiredDefault = false
export const hogFunctionsRearrangePartialUpdateBodyInputsSchemaItemSecretDefault = false
export const hogFunctionsRearrangePartialUpdateBodyInputsSchemaItemHiddenDefault = false
export const hogFunctionsRearrangePartialUpdateBodyFiltersSourceDefault = `events`
export const hogFunctionsRearrangePartialUpdateBodyMaskingOneTtlMin = 60
export const hogFunctionsRearrangePartialUpdateBodyMaskingOneTtlMax = 86400

export const hogFunctionsRearrangePartialUpdateBodyMappingsItemInputsSchemaItemRequiredDefault = false
export const hogFunctionsRearrangePartialUpdateBodyMappingsItemInputsSchemaItemSecretDefault = false
export const hogFunctionsRearrangePartialUpdateBodyMappingsItemInputsSchemaItemHiddenDefault = false
export const hogFunctionsRearrangePartialUpdateBodyMappingsItemFiltersSourceDefault = `events`
export const hogFunctionsRearrangePartialUpdateBodyTemplateIdMax = 400

export const hogFunctionsRearrangePartialUpdateBodyExecutionOrderMin = 0
export const hogFunctionsRearrangePartialUpdateBodyExecutionOrderMax = 32767

export const HogFunctionsRearrangePartialUpdateBody = /* @__PURE__ */ zod.object({
    type: zod
        .union([
            zod
                .enum([
                    'destination',
                    'site_destination',
                    'internal_destination',
                    'source_webhook',
                    'warehouse_source_webhook',
                    'site_app',
                    'transformation',
                ])
                .describe(
                    '* `destination` - Destination\n* `site_destination` - Site Destination\n* `internal_destination` - Internal Destination\n* `source_webhook` - Source Webhook\n* `warehouse_source_webhook` - Warehouse Source Webhook\n* `site_app` - Site App\n* `transformation` - Transformation'
                ),
            zod.literal(null),
        ])
        .nullish(),
    name: zod.string().max(hogFunctionsRearrangePartialUpdateBodyNameMax).nullish(),
    description: zod.string().optional(),
    enabled: zod.boolean().optional(),
    deleted: zod.boolean().optional(),
    hog: zod.string().optional(),
    inputs_schema: zod
        .array(
            zod.object({
                type: zod
                    .enum([
                        'string',
                        'number',
                        'boolean',
                        'dictionary',
                        'choice',
                        'json',
                        'integration',
                        'integration_field',
                        'email',
                        'native_email',
                    ])
                    .describe(
                        '* `string` - string\n* `number` - number\n* `boolean` - boolean\n* `dictionary` - dictionary\n* `choice` - choice\n* `json` - json\n* `integration` - integration\n* `integration_field` - integration_field\n* `email` - email\n* `native_email` - native_email'
                    ),
                key: zod.string(),
                label: zod.string().optional(),
                choices: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                required: zod.boolean().default(hogFunctionsRearrangePartialUpdateBodyInputsSchemaItemRequiredDefault),
                default: zod.unknown().optional(),
                secret: zod.boolean().default(hogFunctionsRearrangePartialUpdateBodyInputsSchemaItemSecretDefault),
                hidden: zod.boolean().default(hogFunctionsRearrangePartialUpdateBodyInputsSchemaItemHiddenDefault),
                description: zod.string().optional(),
                integration: zod.string().optional(),
                integration_key: zod.string().optional(),
                requires_field: zod.string().optional(),
                integration_field: zod.string().optional(),
                requiredScopes: zod.string().optional(),
                templating: zod
                    .union([zod.literal(true), zod.literal(false), zod.literal('hog'), zod.literal('liquid')])
                    .optional()
                    .describe('* `True` - True\n* `False` - False\n* `hog` - hog\n* `liquid` - liquid'),
            })
        )
        .optional(),
    inputs: zod
        .record(
            zod.string(),
            zod.object({
                value: zod.string().optional(),
                templating: zod.enum(['hog', 'liquid']).optional().describe('* `hog` - hog\n* `liquid` - liquid'),
                bytecode: zod.array(zod.unknown()).optional(),
                order: zod.number().optional(),
                transpiled: zod.unknown().optional(),
            })
        )
        .optional(),
    filters: zod
        .object({
            source: zod
                .enum(['events', 'person-updates', 'data-warehouse-table'])
                .describe(
                    '* `events` - events\n* `person-updates` - person-updates\n* `data-warehouse-table` - data-warehouse-table'
                )
                .default(hogFunctionsRearrangePartialUpdateBodyFiltersSourceDefault),
            actions: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            events: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            data_warehouse: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            properties: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
            bytecode: zod.unknown().nullish(),
            transpiled: zod.unknown().optional(),
            filter_test_accounts: zod.boolean().optional(),
            bytecode_error: zod.string().optional(),
        })
        .optional(),
    masking: zod
        .object({
            ttl: zod
                .number()
                .min(hogFunctionsRearrangePartialUpdateBodyMaskingOneTtlMin)
                .max(hogFunctionsRearrangePartialUpdateBodyMaskingOneTtlMax),
            threshold: zod.number().nullish(),
            hash: zod.string(),
            bytecode: zod.unknown().nullish(),
        })
        .nullish(),
    mappings: zod
        .array(
            zod.object({
                name: zod.string().optional(),
                inputs_schema: zod
                    .array(
                        zod.object({
                            type: zod
                                .enum([
                                    'string',
                                    'number',
                                    'boolean',
                                    'dictionary',
                                    'choice',
                                    'json',
                                    'integration',
                                    'integration_field',
                                    'email',
                                    'native_email',
                                ])
                                .describe(
                                    '* `string` - string\n* `number` - number\n* `boolean` - boolean\n* `dictionary` - dictionary\n* `choice` - choice\n* `json` - json\n* `integration` - integration\n* `integration_field` - integration_field\n* `email` - email\n* `native_email` - native_email'
                                ),
                            key: zod.string(),
                            label: zod.string().optional(),
                            choices: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                            required: zod
                                .boolean()
                                .default(
                                    hogFunctionsRearrangePartialUpdateBodyMappingsItemInputsSchemaItemRequiredDefault
                                ),
                            default: zod.unknown().optional(),
                            secret: zod
                                .boolean()
                                .default(
                                    hogFunctionsRearrangePartialUpdateBodyMappingsItemInputsSchemaItemSecretDefault
                                ),
                            hidden: zod
                                .boolean()
                                .default(
                                    hogFunctionsRearrangePartialUpdateBodyMappingsItemInputsSchemaItemHiddenDefault
                                ),
                            description: zod.string().optional(),
                            integration: zod.string().optional(),
                            integration_key: zod.string().optional(),
                            requires_field: zod.string().optional(),
                            integration_field: zod.string().optional(),
                            requiredScopes: zod.string().optional(),
                            templating: zod
                                .union([
                                    zod.literal(true),
                                    zod.literal(false),
                                    zod.literal('hog'),
                                    zod.literal('liquid'),
                                ])
                                .optional()
                                .describe('* `True` - True\n* `False` - False\n* `hog` - hog\n* `liquid` - liquid'),
                        })
                    )
                    .optional(),
                inputs: zod
                    .record(
                        zod.string(),
                        zod.object({
                            value: zod.string().optional(),
                            templating: zod
                                .enum(['hog', 'liquid'])
                                .optional()
                                .describe('* `hog` - hog\n* `liquid` - liquid'),
                            bytecode: zod.array(zod.unknown()).optional(),
                            order: zod.number().optional(),
                            transpiled: zod.unknown().optional(),
                        })
                    )
                    .optional(),
                filters: zod
                    .object({
                        source: zod
                            .enum(['events', 'person-updates', 'data-warehouse-table'])
                            .describe(
                                '* `events` - events\n* `person-updates` - person-updates\n* `data-warehouse-table` - data-warehouse-table'
                            )
                            .default(hogFunctionsRearrangePartialUpdateBodyMappingsItemFiltersSourceDefault),
                        actions: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        events: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        data_warehouse: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        properties: zod.array(zod.record(zod.string(), zod.unknown())).optional(),
                        bytecode: zod.unknown().nullish(),
                        transpiled: zod.unknown().optional(),
                        filter_test_accounts: zod.boolean().optional(),
                        bytecode_error: zod.string().optional(),
                    })
                    .optional(),
            })
        )
        .nullish(),
    icon_url: zod.string().nullish(),
    template_id: zod.string().max(hogFunctionsRearrangePartialUpdateBodyTemplateIdMax).nullish(),
    execution_order: zod
        .number()
        .min(hogFunctionsRearrangePartialUpdateBodyExecutionOrderMin)
        .max(hogFunctionsRearrangePartialUpdateBodyExecutionOrderMax)
        .nullish(),
    _create_in_folder: zod.string().optional(),
})
