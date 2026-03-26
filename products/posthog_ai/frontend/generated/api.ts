import { apiMutator } from '../../../../frontend/src/lib/api-orval-mutator'
/**
 * Auto-generated from the Django backend OpenAPI schema.
 * To modify these types, update the Django serializers or views, then run:
 *   hogli build:openapi
 * Questions or issues? #team-devex on Slack
 *
 * PostHog API - generated
 * OpenAPI spec version: 1.0.0
 */
import type {
    ActionPredictionConfigApi,
    ActionPredictionConfigsListParams,
    ActionPredictionModelApi,
    ActionPredictionModelsListParams,
    PaginatedActionPredictionConfigListListApi,
    PaginatedActionPredictionModelListListApi,
} from './api.schemas'

// https://stackoverflow.com/questions/49579094/typescript-conditional-types-filter-out-readonly-properties-pick-only-requir/49579497#49579497
type IfEquals<X, Y, A = X, B = never> = (<T>() => T extends X ? 1 : 2) extends <T>() => T extends Y ? 1 : 2 ? A : B

type WritableKeys<T> = {
    [P in keyof T]-?: IfEquals<{ [Q in P]: T[P] }, { -readonly [Q in P]: T[P] }, P>
}[keyof T]

type UnionToIntersection<U> = (U extends any ? (k: U) => void : never) extends (k: infer I) => void ? I : never
type DistributeReadOnlyOverUnions<T> = T extends any ? NonReadonly<T> : never

type Writable<T> = Pick<T, WritableKeys<T>>
type NonReadonly<T> = [T] extends [UnionToIntersection<T>]
    ? {
          [P in keyof Writable<T>]: T[P] extends object ? NonReadonly<NonNullable<T[P]>> : T[P]
      }
    : DistributeReadOnlyOverUnions<T>

export const getActionPredictionConfigsListUrl = (projectId: string, params?: ActionPredictionConfigsListParams) => {
    const normalizedParams = new URLSearchParams()

    Object.entries(params || {}).forEach(([key, value]) => {
        if (value !== undefined) {
            normalizedParams.append(key, value === null ? 'null' : value.toString())
        }
    })

    const stringifiedParams = normalizedParams.toString()

    return stringifiedParams.length > 0
        ? `/api/environments/${projectId}/action_prediction_configs/?${stringifiedParams}`
        : `/api/environments/${projectId}/action_prediction_configs/`
}

export const actionPredictionConfigsList = async (
    projectId: string,
    params?: ActionPredictionConfigsListParams,
    options?: RequestInit
): Promise<PaginatedActionPredictionConfigListListApi> => {
    return apiMutator<PaginatedActionPredictionConfigListListApi>(
        getActionPredictionConfigsListUrl(projectId, params),
        {
            ...options,
            method: 'GET',
        }
    )
}

export const getActionPredictionConfigsCreateUrl = (projectId: string) => {
    return `/api/environments/${projectId}/action_prediction_configs/`
}

export const actionPredictionConfigsCreate = async (
    projectId: string,
    actionPredictionConfigApi: NonReadonly<ActionPredictionConfigApi>,
    options?: RequestInit
): Promise<ActionPredictionConfigApi> => {
    return apiMutator<ActionPredictionConfigApi>(getActionPredictionConfigsCreateUrl(projectId), {
        ...options,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...options?.headers },
        body: JSON.stringify(actionPredictionConfigApi),
    })
}

export const getActionPredictionModelsListUrl = (projectId: string, params?: ActionPredictionModelsListParams) => {
    const normalizedParams = new URLSearchParams()

    Object.entries(params || {}).forEach(([key, value]) => {
        if (value !== undefined) {
            normalizedParams.append(key, value === null ? 'null' : value.toString())
        }
    })

    const stringifiedParams = normalizedParams.toString()

    return stringifiedParams.length > 0
        ? `/api/environments/${projectId}/action_prediction_models/?${stringifiedParams}`
        : `/api/environments/${projectId}/action_prediction_models/`
}

export const actionPredictionModelsList = async (
    projectId: string,
    params?: ActionPredictionModelsListParams,
    options?: RequestInit
): Promise<PaginatedActionPredictionModelListListApi> => {
    return apiMutator<PaginatedActionPredictionModelListListApi>(getActionPredictionModelsListUrl(projectId, params), {
        ...options,
        method: 'GET',
    })
}

export const getActionPredictionModelsCreateUrl = (projectId: string) => {
    return `/api/environments/${projectId}/action_prediction_models/`
}

export const actionPredictionModelsCreate = async (
    projectId: string,
    actionPredictionModelApi: NonReadonly<ActionPredictionModelApi>,
    options?: RequestInit
): Promise<ActionPredictionModelApi> => {
    return apiMutator<ActionPredictionModelApi>(getActionPredictionModelsCreateUrl(projectId), {
        ...options,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...options?.headers },
        body: JSON.stringify(actionPredictionModelApi),
    })
}

/**
 * Invoke an MCP tool by name.

This endpoint allows MCP callers to invoke Max AI tools directly
without going through the full LangChain conversation flow.

Scopes are resolved dynamically per tool via dangerously_get_required_scopes.
 */
export const getMcpToolsCreateUrl = (projectId: string, toolName: string) => {
    return `/api/environments/${projectId}/mcp_tools/${toolName}/`
}

export const mcpToolsCreate = async (projectId: string, toolName: string, options?: RequestInit): Promise<void> => {
    return apiMutator<void>(getMcpToolsCreateUrl(projectId, toolName), {
        ...options,
        method: 'POST',
    })
}
