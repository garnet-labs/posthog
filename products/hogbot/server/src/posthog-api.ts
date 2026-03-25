import type { HogbotBusyState } from './types'

export interface PostHogApiClientOptions {
    apiUrl: string
    apiKey: string
    teamId: number
}

export class PostHogApiClient {
    constructor(private readonly options: PostHogApiClientOptions) {}

    async registerServer(args: {
        sandboxUrl: string
        sandboxConnectToken?: string | null
        status: string
    }): Promise<void> {
        await this.request(`/server/register/`, {
            method: 'POST',
            body: {
                sandbox_url: args.sandboxUrl,
                sandbox_connect_token: args.sandboxConnectToken ?? null,
                status: args.status,
            },
        })
    }

    async heartbeat(args: {
        status: string
        busy: HogbotBusyState
        activeSignalId?: string | null
        lastError?: string | null
    }): Promise<void> {
        await this.request(`/server/heartbeat/`, {
            method: 'POST',
            body: {
                status: args.status,
                busy: args.busy,
                active_signal_id: args.activeSignalId ?? null,
                last_error: args.lastError ?? null,
            },
        })
    }

    async unregisterServer(): Promise<void> {
        await this.request(`/server/unregister/`, {
            method: 'POST',
            body: {},
        })
    }

    async appendAdminLog(entries: unknown[]): Promise<void> {
        await this.request(`/admin/append_log/`, {
            method: 'POST',
            body: { entries },
        })
    }

    async appendResearchLog(signalId: string, entries: unknown[]): Promise<void> {
        await this.request(`/research/${encodeURIComponent(signalId)}/append_log/`, {
            method: 'POST',
            body: { entries },
        })
    }

    private async request(path: string, options: { method: string; body?: unknown }): Promise<void> {
        const url = `${this.options.apiUrl.replace(/\/$/, '')}/api/projects/${this.options.teamId}/hogbot${path}`
        const response = await fetch(url, {
            method: options.method,
            headers: {
                Authorization: `Bearer ${this.options.apiKey}`,
                'Content-Type': 'application/json',
            },
            body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
        })

        if (!response.ok) {
            const body = await response.text()
            throw new Error(`PostHog API request failed (${response.status}): ${body}`)
        }
    }
}
