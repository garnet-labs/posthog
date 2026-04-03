/**
 * Loads the CLI manifest — a generated JSON file mapping tool names to HTTP
 * details (method, path, params) plus metadata (description, category, scopes).
 *
 * The manifest is produced by `generate-tools.ts` alongside the MCP handlers,
 * so it reflects the same YAML + OpenAPI resolution (skips, overrides, etc.).
 */

import * as fs from 'node:fs'
import * as path from 'node:path'

export interface CliToolManifest {
    method: string
    path: string
    title: string
    description: string
    category: string
    feature: string
    scopes: string[]
    annotations: {
        readOnly: boolean
        destructive: boolean
        idempotent: boolean
    }
    params: {
        path: string[]
        query: string[]
        body: string[]
    }
    soft_delete?: string | boolean
}

const MANIFEST_LOCATIONS = [
    // Running from services/cli/src/ (dev with tsx)
    path.resolve(__dirname, '../../mcp/schema/cli-manifest.json'),
    // Running from services/cli/dist/ (built)
    path.resolve(__dirname, '../../../mcp/schema/cli-manifest.json'),
]

export function loadManifest(): Record<string, CliToolManifest> {
    for (const loc of MANIFEST_LOCATIONS) {
        if (fs.existsSync(loc)) {
            return JSON.parse(fs.readFileSync(loc, 'utf-8'))
        }
    }
    throw new Error(
        `CLI manifest not found. Run "hogli build:openapi" to generate it.\nSearched: ${MANIFEST_LOCATIONS.join(', ')}`
    )
}
