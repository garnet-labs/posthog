import { z } from 'zod'

import type { Schemas } from '@/api/generated'

/**
 * The generated Schemas.Insight has many fields incorrectly typed as `string`
 * due to missing @extend_schema_field decorators on the Django serializer's
 * SerializerMethodFields. This type corrects those fields and adds fields
 * that are excluded from the OpenAPI schema but returned at runtime.
 */
export type Insight = Omit<
    Schemas.Insight,
    | 'result'
    | 'hasMore'
    | 'columns'
    | 'is_cached'
    | 'query_status'
    | 'hogql'
    | 'types'
    | 'resolved_date_range'
    | 'alerts'
    | 'last_viewed_at'
    | 'last_refresh'
    | 'cache_target_age'
    | 'next_allowed_client_refresh'
> & {
    result: unknown
    hasMore: boolean | null
    columns: unknown[] | null
    is_cached: boolean
    query_status: Record<string, unknown> | null
    hogql: string | null
    types: unknown[] | null
    resolved_date_range: { date_from: string; date_to: string } | null
    alerts: unknown[]
    last_viewed_at: string | null
    last_refresh: string | null
    cache_target_age: string | null
    next_allowed_client_refresh: string | null
    filters: Record<string, unknown>
    refreshing: boolean | null
    saved: boolean
}

export const CreateInsightInputSchema = z.object({
    name: z.string(),
    query: z
        .object({
            kind: z.union([z.literal('InsightVizNode'), z.literal('DataVisualizationNode')]),
            source: z
                .any()
                .describe(
                    'The inner query you validated with `query-run`. For InsightVizNode use a TrendsQuery/FunnelsQuery/PathsQuery; for DataVisualizationNode use a HogQLQuery.'
                ), // NOTE: This is intentionally z.any() to avoid populating the context with the complicated query schema, but we prompt the LLM to use 'query-run' to check queries, before creating insights.
            display: z
                .string()
                .optional()
                .describe(
                    'ONLY for DataVisualizationNode (HogQL-backed insights). Sets the visualization type. IMPORTANT: a DataVisualizationNode with no `display` renders as a table — you must set this (e.g. "ActionsLineGraph", "ActionsBar", "ActionsAreaGraph", "ActionsPie", "BoldNumber") whenever the user asks for a chart. Leave unset on InsightVizNode, which derives its display from the inner query.'
                ),
            chartSettings: z
                .record(z.string(), z.any())
                .optional()
                .describe(
                    'ONLY for DataVisualizationNode when `display` is a chart (line/bar/area/etc.). Maps HogQL columns to chart axes: `{ xAxis: { column: "day" }, yAxis: [{ column: "signups" }] }`. Without this, line/bar charts will not know which columns to plot.'
                ),
            tableSettings: z
                .record(z.string(), z.any())
                .optional()
                .describe(
                    'ONLY for DataVisualizationNode when `display` is ActionsTable. Optional column pinning, transpose, etc.'
                ),
        })
        .describe(
            'The insight query. For HogQL queries wrapped in DataVisualizationNode, remember to set `display` (and `chartSettings.xAxis`/`yAxis` for line/bar/area charts) — otherwise the insight renders as a table even if the user asked for a chart.'
        ),
    description: z.string().optional(),
    favorited: z.boolean(),
    tags: z.array(z.string()).optional(),
})

export const UpdateInsightInputSchema = z.object({
    name: z.string().optional(),
    description: z.string().optional(),
    filters: z.record(z.string(), z.any()).optional(),
    query: z
        .object({
            kind: z.union([z.literal('InsightVizNode'), z.literal('DataVisualizationNode')]),
            source: z
                .any()
                .describe(
                    'The inner query (TrendsQuery/FunnelsQuery/PathsQuery for InsightVizNode, HogQLQuery for DataVisualizationNode). On updates the existing query can optionally be reused.'
                ), // NOTE: This is intentionally z.any() to avoid populating the context with the complicated query schema, and to allow the LLM to make a change to an existing insight whose schema we do not support in our simplified subset of the full insight schema.
            display: z
                .string()
                .optional()
                .describe(
                    'ONLY for DataVisualizationNode. Set to e.g. "ActionsLineGraph", "ActionsBar", "ActionsAreaGraph", "ActionsPie", "BoldNumber" to render the HogQL result as a chart. Omit (or "ActionsTable") for a table. Leave unset on InsightVizNode.'
                ),
            chartSettings: z
                .record(z.string(), z.any())
                .optional()
                .describe(
                    'ONLY for DataVisualizationNode chart displays. Maps HogQL columns to axes, e.g. `{ xAxis: { column: "day" }, yAxis: [{ column: "count" }] }`.'
                ),
            tableSettings: z
                .record(z.string(), z.any())
                .optional()
                .describe('ONLY for DataVisualizationNode table displays.'),
        })
        .optional(),
    favorited: z.boolean().optional(),
    dashboards: z
        .array(z.number())
        .optional()
        .describe(
            'Dashboard IDs this insight should belong to. This is a full replacement — always include all existing dashboard IDs when adding a new one.'
        ),
    tags: z.array(z.string()).optional(),
})

export const ListInsightsSchema = z.object({
    limit: z.number().optional(),
    offset: z.number().optional(),
    favorited: z.boolean().optional(),
    search: z.string().optional(),
})

export type CreateInsightInput = z.infer<typeof CreateInsightInputSchema>
export type UpdateInsightInput = z.infer<typeof UpdateInsightInputSchema>
export type ListInsightsData = z.infer<typeof ListInsightsSchema>

export type SQLInsightResponse = Array<{
    type: string
    data: Record<string, unknown>
}>
