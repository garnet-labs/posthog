#!/usr/bin/env node
/**
 * `ph` — Agent-first CLI for the PostHog API.
 *
 * Reads a generated manifest (cli-manifest.json) that maps tool names to HTTP
 * method + path + param locations. Accepts raw JSON payloads via --json,
 * avoiding flag-per-param explosion. Designed for coding agents (Claude Code,
 * Cursor, etc.) that interact via bash.
 *
 * Usage:
 *   ph list                                      # discover tools
 *   ph schema feature-flag-get-all                # inspect input params
 *   ph feature-flag-get-all --json '{"search":"beta"}'
 *   ph feature-flag-get-all --json '{"search":"beta"}' --dry-run
 */

import { Command } from 'commander'

import { resolveConfig, type CliConfig } from './config.js'
import { execute, dryRun } from './executor.js'
import { loadManifest, type CliToolManifest } from './manifest.js'

function createProgram(manifest: Record<string, CliToolManifest>, config: CliConfig): Command {
    const program = new Command()
    program.name('ph').description('Agent-first CLI for the PostHog API').version('0.1.0')

    // --- ph list ---
    program
        .command('list')
        .description('List available tools, grouped by category')
        .option('--category <name>', 'Filter by category name')
        .option('--json', 'Output as JSON')
        .action((opts: { category?: string; json?: boolean }) => {
            const tools = Object.entries(manifest)
            const filtered = opts.category
                ? tools.filter(([, t]) => t.category.toLowerCase() === opts.category!.toLowerCase())
                : tools

            if (opts.json) {
                const out = filtered.map(([name, t]) => ({
                    name,
                    title: t.title,
                    category: t.category,
                    method: t.method,
                    readOnly: t.annotations.readOnly,
                    destructive: t.annotations.destructive,
                }))
                process.stdout.write(JSON.stringify(out, null, 2) + '\n')
                return
            }

            // Group by category for human-readable output
            const byCategory = new Map<string, [string, CliToolManifest][]>()
            for (const entry of filtered) {
                const cat = entry[1].category
                if (!byCategory.has(cat)) {
                    byCategory.set(cat, [])
                }
                byCategory.get(cat)!.push(entry)
            }

            for (const [cat, entries] of byCategory) {
                process.stdout.write(`\n${cat}\n`)
                for (const [name, t] of entries) {
                    const flags = [
                        t.annotations.readOnly ? 'read' : 'write',
                        t.annotations.destructive ? 'destructive' : '',
                    ]
                        .filter(Boolean)
                        .join(', ')
                    process.stdout.write(`  ${name.padEnd(40)} ${t.title} (${flags})\n`)
                }
            }
            process.stdout.write('\n')
        })

    // --- ph schema <tool> ---
    program
        .command('schema <tool>')
        .description('Show input schema for a tool (params, method, path)')
        .action((toolName: string) => {
            const tool = manifest[toolName]
            if (!tool) {
                process.stderr.write(`Unknown tool: ${toolName}\n`)
                process.stderr.write(`Run "ph list" to see available tools.\n`)
                process.exitCode = 1
                return
            }
            const schema = {
                name: toolName,
                title: tool.title,
                description: tool.description,
                method: tool.method,
                path: tool.path,
                category: tool.category,
                scopes: tool.scopes,
                annotations: tool.annotations,
                params: tool.params,
                ...(tool.soft_delete ? { soft_delete: tool.soft_delete } : {}),
            }
            process.stdout.write(JSON.stringify(schema, null, 2) + '\n')
        })

    // --- ph <tool> --json '{...}' [--dry-run] ---
    program
        .command('exec <tool>')
        .description('Execute a tool with a JSON payload')
        .requiredOption('--json <payload>', 'JSON input payload')
        .option('--dry-run', 'Validate and show the request without executing')
        .option('--fields <mask>', 'Comma-separated list of fields to include in output')
        .action(async (toolName: string, opts: { json: string; dryRun?: boolean; fields?: string }) => {
            const tool = manifest[toolName]
            if (!tool) {
                process.stderr.write(`Unknown tool: ${toolName}\n`)
                process.exitCode = 1
                return
            }

            let params: Record<string, unknown>
            try {
                params = JSON.parse(opts.json)
            } catch {
                process.stderr.write(`Invalid JSON payload: ${opts.json}\n`)
                process.exitCode = 1
                return
            }

            if (opts.dryRun) {
                const preview = dryRun(tool, params, config)
                process.stdout.write(JSON.stringify(preview, null, 2) + '\n')
                return
            }

            try {
                const result = await execute(tool, params, config)
                const output = opts.fields ? filterFields(result, opts.fields) : result
                process.stdout.write(JSON.stringify(output, null, 2) + '\n')
            } catch (err) {
                const message = err instanceof Error ? err.message : String(err)
                process.stderr.write(`Error: ${message}\n`)
                process.exitCode = 1
            }
        })

    return program
}

function filterFields(data: unknown, fields: string): unknown {
    if (typeof data !== 'object' || data === null) {
        return data
    }
    const fieldSet = new Set(fields.split(',').map((f) => f.trim()))
    const record = data as Record<string, unknown>
    const filtered: Record<string, unknown> = {}
    for (const key of fieldSet) {
        if (key in record) {
            filtered[key] = record[key]
        }
    }
    // Preserve pagination metadata if present
    if ('next' in record) {
        filtered['next'] = record['next']
    }
    if ('previous' in record) {
        filtered['previous'] = record['previous']
    }
    if ('count' in record) {
        filtered['count'] = record['count']
    }
    return filtered
}

function rewriteShorthand(argv: string[], manifest: Record<string, CliToolManifest>): string[] {
    // If the first positional arg (after node + script) is a known tool name,
    // rewrite `ph <tool> --json ...` → `ph exec <tool> --json ...`
    const builtins = new Set(['list', 'schema', 'exec', 'help', '--help', '-h', '-V', '--version'])
    const firstArg = argv[2]
    if (firstArg && !builtins.has(firstArg) && !firstArg.startsWith('-') && manifest[firstArg]) {
        return [...argv.slice(0, 2), 'exec', ...argv.slice(2)]
    }
    return argv
}

async function main(): Promise<void> {
    const manifest = loadManifest()
    // Defer config resolution — list and schema don't need API credentials
    const config = new Proxy({} as CliConfig, {
        get(_target, prop) {
            const resolved = resolveConfig()
            return resolved[prop as keyof CliConfig]
        },
    })
    const program = createProgram(manifest, config)
    const argv = rewriteShorthand(process.argv, manifest)
    await program.parseAsync(argv)
}

main().catch((err) => {
    process.stderr.write(`Fatal: ${err}\n`)
    process.exit(1)
})
