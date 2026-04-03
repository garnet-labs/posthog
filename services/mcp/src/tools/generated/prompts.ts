// AUTO-GENERATED from products/llm_analytics/mcp/prompts.yaml + OpenAPI — do not edit
import { z } from 'zod'

import type { Schemas } from '@/api/generated'
import { LlmPromptsCreateBody, LlmPromptsNameRetrieveParams } from '@/generated/prompts/api'
import type { Context, ToolBase, ZodObjectAny } from '@/tools/types'

const PromptListSchema = z.object({})

const promptList = (): ToolBase<typeof PromptListSchema, Schemas.PaginatedLLMPromptList> => ({
    name: 'prompt-list',
    schema: PromptListSchema,
    // eslint-disable-next-line no-unused-vars
    handler: async (context: Context, params: z.infer<typeof PromptListSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.PaginatedLLMPromptList>({
            method: 'GET',
            path: `/api/environments/${projectId}/llm_prompts/`,
        })
        return result
    },
})

const PromptGetSchema = LlmPromptsNameRetrieveParams.omit({ project_id: true })

const promptGet = (): ToolBase<typeof PromptGetSchema, Schemas.LLMPrompt> => ({
    name: 'prompt-get',
    schema: PromptGetSchema,
    handler: async (context: Context, params: z.infer<typeof PromptGetSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const result = await context.api.request<Schemas.LLMPrompt>({
            method: 'GET',
            path: `/api/environments/${projectId}/llm_prompts/name/${params.prompt_name}/`,
        })
        return result
    },
})

const PromptCreateSchema = LlmPromptsCreateBody.omit({ deleted: true })

const promptCreate = (): ToolBase<typeof PromptCreateSchema, Schemas.LLMPrompt> => ({
    name: 'prompt-create',
    schema: PromptCreateSchema,
    handler: async (context: Context, params: z.infer<typeof PromptCreateSchema>) => {
        const projectId = await context.stateManager.getProjectId()
        const body: Record<string, unknown> = {}
        if (params.name !== undefined) {
            body['name'] = params.name
        }
        if (params.prompt !== undefined) {
            body['prompt'] = params.prompt
        }
        const result = await context.api.request<Schemas.LLMPrompt>({
            method: 'POST',
            path: `/api/environments/${projectId}/llm_prompts/`,
            body,
        })
        return result
    },
})

export const GENERATED_TOOLS: Record<string, () => ToolBase<ZodObjectAny>> = {
    'prompt-list': promptList,
    'prompt-get': promptGet,
    'prompt-create': promptCreate,
}
