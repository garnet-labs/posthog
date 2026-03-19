/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 5 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const LogsAlertsListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const LogsAlertsListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

export const LogsAlertsCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const logsAlertsCreateBodyNameMax = 255

export const logsAlertsCreateBodyEnabledDefault = true
export const logsAlertsCreateBodyThresholdOperatorDefault = `above`
export const logsAlertsCreateBodyWindowMinutesDefault = 5
export const logsAlertsCreateBodyEvaluationPeriodsDefault = 1
export const logsAlertsCreateBodyEvaluationPeriodsMax = 10

export const logsAlertsCreateBodyDatapointsToAlarmDefault = 1
export const logsAlertsCreateBodyDatapointsToAlarmMax = 10

export const logsAlertsCreateBodyCooldownMinutesDefault = 0
export const logsAlertsCreateBodyCooldownMinutesMin = 0

export const LogsAlertsCreateBody = /* @__PURE__ */ zod.object({
    name: zod.string().max(logsAlertsCreateBodyNameMax).describe('Human-readable name for this alert.'),
    enabled: zod
        .boolean()
        .default(logsAlertsCreateBodyEnabledDefault)
        .describe('Whether the alert is actively being evaluated. Disabling resets the state to not_firing.'),
    filters: zod
        .unknown()
        .describe(
            'Filter criteria — subset of LogsViewerFilters. Must contain at least one of: severityLevels (list of severity strings), serviceNames (list of service name strings), or filterGroup (property filter group object).'
        ),
    threshold_count: zod
        .number()
        .min(1)
        .describe('Number of matching log entries that constitutes a threshold breach within the evaluation window.'),
    threshold_operator: zod
        .enum(['above', 'below'])
        .describe('* `above` - Above\n* `below` - Below')
        .default(logsAlertsCreateBodyThresholdOperatorDefault)
        .describe(
            'Whether the alert fires when the count is above or below the threshold.\n\n* `above` - Above\n* `below` - Below'
        ),
    window_minutes: zod
        .number()
        .default(logsAlertsCreateBodyWindowMinutesDefault)
        .describe('Time window in minutes over which log entries are counted. Allowed values: 1, 5, 10, 15, 30, 60.'),
    evaluation_periods: zod
        .number()
        .min(1)
        .max(logsAlertsCreateBodyEvaluationPeriodsMax)
        .default(logsAlertsCreateBodyEvaluationPeriodsDefault)
        .describe('Total number of check periods in the sliding evaluation window for firing (M in N-of-M).'),
    datapoints_to_alarm: zod
        .number()
        .min(1)
        .max(logsAlertsCreateBodyDatapointsToAlarmMax)
        .default(logsAlertsCreateBodyDatapointsToAlarmDefault)
        .describe('How many periods within the evaluation window must breach the threshold to fire (N in N-of-M).'),
    cooldown_minutes: zod
        .number()
        .min(logsAlertsCreateBodyCooldownMinutesMin)
        .default(logsAlertsCreateBodyCooldownMinutesDefault)
        .describe('Minimum minutes between repeated notifications after the alert fires. 0 means no cooldown.'),
    snooze_until: zod.iso
        .datetime({})
        .nullish()
        .describe('ISO 8601 timestamp until which the alert is snoozed. Set to null to unsnooze.'),
})

export const LogsAlertsRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this logs alert configuration.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const LogsAlertsPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this logs alert configuration.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const logsAlertsPartialUpdateBodyNameMax = 255

export const logsAlertsPartialUpdateBodyEvaluationPeriodsMax = 10

export const logsAlertsPartialUpdateBodyDatapointsToAlarmMax = 10

export const logsAlertsPartialUpdateBodyCooldownMinutesMin = 0

export const LogsAlertsPartialUpdateBody = /* @__PURE__ */ zod.object({
    name: zod
        .string()
        .max(logsAlertsPartialUpdateBodyNameMax)
        .optional()
        .describe('Human-readable name for this alert.'),
    enabled: zod
        .boolean()
        .optional()
        .describe('Whether the alert is actively being evaluated. Disabling resets the state to not_firing.'),
    filters: zod
        .unknown()
        .optional()
        .describe(
            'Filter criteria — subset of LogsViewerFilters. Must contain at least one of: severityLevels (list of severity strings), serviceNames (list of service name strings), or filterGroup (property filter group object).'
        ),
    threshold_count: zod
        .number()
        .min(1)
        .optional()
        .describe('Number of matching log entries that constitutes a threshold breach within the evaluation window.'),
    threshold_operator: zod
        .enum(['above', 'below'])
        .describe('* `above` - Above\n* `below` - Below')
        .optional()
        .describe(
            'Whether the alert fires when the count is above or below the threshold.\n\n* `above` - Above\n* `below` - Below'
        ),
    window_minutes: zod
        .number()
        .optional()
        .describe('Time window in minutes over which log entries are counted. Allowed values: 1, 5, 10, 15, 30, 60.'),
    evaluation_periods: zod
        .number()
        .min(1)
        .max(logsAlertsPartialUpdateBodyEvaluationPeriodsMax)
        .optional()
        .describe('Total number of check periods in the sliding evaluation window for firing (M in N-of-M).'),
    datapoints_to_alarm: zod
        .number()
        .min(1)
        .max(logsAlertsPartialUpdateBodyDatapointsToAlarmMax)
        .optional()
        .describe('How many periods within the evaluation window must breach the threshold to fire (N in N-of-M).'),
    cooldown_minutes: zod
        .number()
        .min(logsAlertsPartialUpdateBodyCooldownMinutesMin)
        .optional()
        .describe('Minimum minutes between repeated notifications after the alert fires. 0 means no cooldown.'),
    snooze_until: zod.iso
        .datetime({})
        .nullish()
        .describe('ISO 8601 timestamp until which the alert is snoozed. Set to null to unsnooze.'),
})

export const LogsAlertsDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this logs alert configuration.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})
