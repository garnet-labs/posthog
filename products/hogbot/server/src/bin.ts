import { HogbotServer } from './hogbot-server'

function parseArgs(argv: string[]): Record<string, string> {
    const parsed: Record<string, string> = {}
    for (let index = 0; index < argv.length; index += 1) {
        const token = argv[index]
        if (!token.startsWith('--')) {
            continue
        }
        const key = token.slice(2)
        const value = argv[index + 1]
        if (!value || value.startsWith('--')) {
            throw new Error(`Missing value for --${key}`)
        }
        parsed[key] = value
        index += 1
    }
    return parsed
}

function requiredEnv(name: string): string {
    const value = process.env[name]
    if (!value) {
        throw new Error(`Missing required environment variable ${name}`)
    }
    return value
}

async function main(): Promise<void> {
    const values = parseArgs(process.argv.slice(2))

    if (!values.port || !values.teamId || !values.workspacePath || !values.publicBaseUrl) {
        throw new Error('Usage: hogbot-server --port <port> --teamId <id> --workspacePath <path> --publicBaseUrl <url>')
    }

    const server = new HogbotServer({
        port: Number(values.port),
        teamId: Number(values.teamId),
        workspacePath: values.workspacePath,
        publicBaseUrl: values.publicBaseUrl,
        sandboxConnectToken: values.sandboxConnectToken,
        posthogApiUrl: requiredEnv('POSTHOG_API_URL'),
        posthogApiKey: requiredEnv('POSTHOG_PERSONAL_API_KEY'),
    })

    const shutdown = async (): Promise<void> => {
        await server.stop().catch(() => undefined)
        process.exit(0)
    }

    process.on('SIGINT', shutdown)
    process.on('SIGTERM', shutdown)

    await server.start()
}

void main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error))
    process.exit(1)
})
