// AUTO-GENERATED from products/persons/mcp/tools.yaml + OpenAPI — do not edit
import { z } from 'zod'

import type { Schemas } from '@/api/generated'
import {
    PersonsBulkDeleteCreateBody,
    PersonsBulkDeleteCreateQueryParams,
    PersonsDeletePropertyCreateBody,
    PersonsDeletePropertyCreateParams,
    PersonsDeletePropertyCreateQueryParams,
    PersonsListQueryParams,
    PersonsRetrieveParams,
    PersonsUpdatePropertyCreateBody,
    PersonsUpdatePropertyCreateParams,
    PersonsUpdatePropertyCreateQueryParams,
} from '@/generated/persons/api'
import { withPostHogUrl, type WithPostHogUrl } from '@/tools/tool-utils'
import type { Context, ToolBase, ZodObjectAny } from '@/tools/types'

const PersonsListSchema = PersonsListQueryParams.omit({ format: true, properties: true })

const personsList = (): ToolBase<typeof PersonsListSchema, WithPostHogUrl<Schemas.PaginatedPersonList>> => ({
    name: 'persons-list',
    schema: PersonsListSchema,
    handler: async (context: Context, params: z.infer<typeof PersonsListSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.PaginatedPersonList>({
            method: 'GET',
            path: `/api/projects/${projectId}/persons/`,
            query: {
                distinct_id: params.distinct_id,
                email: params.email,
                limit: params.limit,
                offset: params.offset,
                search: params.search,
            },
        })
        return await withPostHogUrl(context, result, '/persons')
    },
})

const PersonsRetrieveSchema = PersonsRetrieveParams.omit({ project_id: true })

const personsRetrieve = (): ToolBase<typeof PersonsRetrieveSchema, WithPostHogUrl<Schemas.Person>> => ({
    name: 'persons-retrieve',
    schema: PersonsRetrieveSchema,
    handler: async (context: Context, params: z.infer<typeof PersonsRetrieveSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.Person>({
            method: 'GET',
            path: `/api/projects/${projectId}/persons/${params.id}/`,
        })
        return await withPostHogUrl(context, result, `/persons/${result.id}`)
    },
})

const PersonsPropertyDeleteSchema = PersonsDeletePropertyCreateParams.omit({ project_id: true })
    .extend(PersonsDeletePropertyCreateQueryParams.omit({ format: true }).shape)
    .extend(PersonsDeletePropertyCreateBody.shape)
    .omit({ $unset: true })
    .extend({ unset: PersonsDeletePropertyCreateBody.shape['$unset'] })

const personsPropertyDelete = (): ToolBase<typeof PersonsPropertyDeleteSchema, unknown> => ({
    name: 'persons-property-delete',
    schema: PersonsPropertyDeleteSchema,
    handler: async (context: Context, params: z.infer<typeof PersonsPropertyDeleteSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.properties !== undefined) {
            body['properties'] = params.properties
        }
        const result = await context.api.request<unknown>({
            method: 'POST',
            path: `/api/projects/${projectId}/persons/${params.id}/delete_property/`,
            body,
            query: {
                $unset: params.$unset,
            },
        })
        return result
    },
})

const PersonsPropertySetSchema = PersonsUpdatePropertyCreateParams.omit({ project_id: true })
    .extend(PersonsUpdatePropertyCreateQueryParams.omit({ format: true }).shape)
    .extend(PersonsUpdatePropertyCreateBody.shape)

const personsPropertySet = (): ToolBase<typeof PersonsPropertySetSchema, unknown> => ({
    name: 'persons-property-set',
    schema: PersonsPropertySetSchema,
    handler: async (context: Context, params: z.infer<typeof PersonsPropertySetSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.properties !== undefined) {
            body['properties'] = params.properties
        }
        const result = await context.api.request<unknown>({
            method: 'POST',
            path: `/api/projects/${projectId}/persons/${params.id}/update_property/`,
            body,
            query: {
                key: params.key,
                value: params.value,
            },
        })
        return result
    },
})

const PersonsBulkDeleteSchema = PersonsBulkDeleteCreateQueryParams.omit({ format: true }).extend(
    PersonsBulkDeleteCreateBody.shape
)

const personsBulkDelete = (): ToolBase<typeof PersonsBulkDeleteSchema, unknown> => ({
    name: 'persons-bulk-delete',
    schema: PersonsBulkDeleteSchema,
    handler: async (context: Context, params: z.infer<typeof PersonsBulkDeleteSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.properties !== undefined) {
            body['properties'] = params.properties
        }
        const result = await context.api.request<unknown>({
            method: 'POST',
            path: `/api/projects/${projectId}/persons/bulk_delete/`,
            body,
            query: {
                delete_events: params.delete_events,
                delete_recordings: params.delete_recordings,
                distinct_ids: params.distinct_ids,
                ids: params.ids,
                keep_person: params.keep_person,
            },
        })
        return result
    },
})

const PersonsCohortsRetrieveSchema = z.object({})

const personsCohortsRetrieve = (): ToolBase<typeof PersonsCohortsRetrieveSchema, unknown> => ({
    name: 'persons-cohorts-retrieve',
    schema: PersonsCohortsRetrieveSchema,
    // eslint-disable-next-line no-unused-vars
    handler: async (context: Context, params: z.infer<typeof PersonsCohortsRetrieveSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<unknown>({
            method: 'GET',
            path: `/api/projects/${projectId}/persons/cohorts/`,
        })
        return result
    },
})

const PersonsValuesRetrieveSchema = z.object({})

const personsValuesRetrieve = (): ToolBase<typeof PersonsValuesRetrieveSchema, unknown> => ({
    name: 'persons-values-retrieve',
    schema: PersonsValuesRetrieveSchema,
    // eslint-disable-next-line no-unused-vars
    handler: async (context: Context, params: z.infer<typeof PersonsValuesRetrieveSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<unknown>({
            method: 'GET',
            path: `/api/projects/${projectId}/persons/values/`,
        })
        return result
    },
})

export const GENERATED_TOOLS: Record<string, () => ToolBase<ZodObjectAny>> = {
    'persons-list': personsList,
    'persons-retrieve': personsRetrieve,
    'persons-property-delete': personsPropertyDelete,
    'persons-property-set': personsPropertySet,
    'persons-bulk-delete': personsBulkDelete,
    'persons-cohorts-retrieve': personsCohortsRetrieve,
    'persons-values-retrieve': personsValuesRetrieve,
}
