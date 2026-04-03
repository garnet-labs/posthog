/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 5 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const ProxyRecordsListParams = /* @__PURE__ */ zod.object({
    organization_id: zod.string(),
})

export const ProxyRecordsListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
})

export const ProxyRecordsCreateParams = /* @__PURE__ */ zod.object({
    organization_id: zod.string(),
})

export const proxyRecordsCreateBodyDomainMax = 64

export const ProxyRecordsCreateBody = /* @__PURE__ */ zod.object({
    domain: zod.string().max(proxyRecordsCreateBodyDomainMax),
})

export const ProxyRecordsRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string(),
    organization_id: zod.string(),
})

export const ProxyRecordsDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.string(),
    organization_id: zod.string(),
})
