declare module '@anthropic-ai/claude-agent-sdk' {
    export type SDKUserMessage = {
        type: 'user'
        message: unknown
        parent_tool_use_id: string | null
        session_id: string
        uuid?: string
    }

    export type SDKMessage =
        | {
              type: 'result'
              subtype: string
              result?: string
              errors?: string[]
          }
        | {
              type: 'system'
              subtype?: string
          }
        | {
              type: 'assistant'
              message?: unknown
          }
        | {
              type: 'stream_event'
              event?: unknown
          }
        | {
              type: 'auth_status'
              error?: string
              output?: string[]
          }

    export type Query = AsyncGenerator<SDKMessage, void> & {
        initializationResult(): Promise<unknown>
        interrupt(): Promise<void>
        close(): void
    }

    export function query(params: {
        prompt: string | AsyncIterable<SDKUserMessage>
        options?: Record<string, unknown>
    }): Query
}
