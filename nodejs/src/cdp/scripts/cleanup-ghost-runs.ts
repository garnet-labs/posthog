/**
 * Ghost Run Cleanup Script
 *
 * Context: During the March 18-19, 2026 incident, a cross-routing bug in the
 * Cyclotron job queue caused workflow invocations to be executed multiple times
 * per trigger event. The bug created 4 parallel execution paths per event (1
 * legitimate + 3 from janitor resets). Each path has its own Cyclotron job ID
 * but shares the same trigger event UUID. These ghost runs are still alive in
 * the Cyclotron database, progressing through delay steps and sending duplicate
 * emails/notifications at each action step.
 *
 * Key insight: Cyclotron job ID = ClickHouse instance_id. The same job ID
 * persists through delay steps (retry in place, not recreated).
 *
 * This script:
 * 1. Takes a ClickHouse CSV export of all log entries containing [Event:] during
 *    the incident window (uses any log message, not just "Resuming workflow")
 * 2. Groups runs by (team_id, workflow_id, event_uuid)
 * 3. For each group with multiple instance_ids, keeps the earliest and marks the rest as ghosts
 * 4. Outputs ghost run IDs that can be marked as 'completed' in the Cyclotron DB
 *    (the IDs match Cyclotron job IDs directly)
 *
 * Usage:
 *   Step 1: Export ClickHouse data to CSV using the query in getClickHouseQuery()
 *   Step 2: Run this script with the CSV to get ghost run IDs
 *   Step 3: Use the generated SQL to clean up the Cyclotron DB
 */
import * as fs from 'fs'
import * as path from 'path'

interface LogEntry {
    team_id: string
    run_id: string
    workflow_id: string
    message: string
    timestamp: string
}

interface GhostRunResult {
    teamId: string
    ghostRunIds: string[]
    legitimateRunId: string
    eventId: string
    totalRuns: number
}

/**
 * Returns the ClickHouse query to extract workflow trigger/resume data
 * for the incident window. Run this on ClickHouse and save the result as CSV.
 */
export function getClickHouseQuery(teamIds?: number[]): string {
    const teamFilter = teamIds?.length ? `  AND team_id IN (${teamIds.join(', ')})` : ''
    return `
SELECT
    team_id,
    instance_id AS run_id,
    log_source_id AS workflow_id,
    message,
    toString(timestamp) AS timestamp
FROM log_entries
WHERE timestamp BETWEEN '2026-03-18 00:00:00' AND '2026-03-31 00:00:00'
  AND log_source = 'hog_flow'
  AND message LIKE '%[Event:%'
${teamFilter}
ORDER BY team_id, message, instance_id
`
}

/**
 * Extracts the event ID from a workflow log message.
 * Messages contain: [Event:EVENT_ID|event_name|timestamp]
 */
export function extractEventId(message: string): string | null {
    const match = message.match(/\[Event:([^|]+)\|/)
    return match ? match[1] : null
}

/**
 * Extracts the action ID from a workflow log message.
 * Messages look like: "Resuming workflow execution at [Action:ACTION_ID] on [Event:...]"
 */
export function extractActionId(message: string): string | null {
    const match = message.match(/\[Action:([^\]]+)\]/)
    return match ? match[1] : null
}

/**
 * Parses CSV data and identifies ghost runs.
 *
 * Groups runs by (team_id, workflow_id, event_id). Within each group,
 * the earliest run (by timestamp) is kept as legitimate, and the rest
 * are marked as ghosts.
 */
export function identifyGhostRuns(entries: LogEntry[]): GhostRunResult[] {
    // Group by team_id + workflow_id + event_id
    const groups = new Map<string, { runId: string; timestamp: string }[]>()

    for (const entry of entries) {
        const eventId = extractEventId(entry.message)
        if (!eventId) {
            continue
        }

        const key = `${entry.team_id}:${entry.workflow_id}:${eventId}`

        if (!groups.has(key)) {
            groups.set(key, [])
        }

        const group = groups.get(key)!
        // Only add each run_id once per group
        if (!group.some((r) => r.runId === entry.run_id)) {
            group.push({ runId: entry.run_id, timestamp: entry.timestamp })
        }
    }

    // For each group with duplicates, identify ghost runs
    const results: GhostRunResult[] = []

    for (const [key, runs] of groups) {
        if (runs.length <= 1) {
            continue
        }

        const parts = key.split(':')
        const teamId = parts[0]
        const eventId = parts.slice(2).join(':')

        // Sort by timestamp, keep the earliest as legitimate
        runs.sort((a, b) => a.timestamp.localeCompare(b.timestamp))

        const legitimateRun = runs[0]
        const ghostRuns = runs.slice(1)

        results.push({
            teamId,
            ghostRunIds: ghostRuns.map((r) => r.runId),
            legitimateRunId: legitimateRun.runId,
            eventId,
            totalRuns: runs.length,
        })
    }

    return results
}

/**
 * Generates SQL to mark ghost runs as completed in the Cyclotron DB.
 * Only updates jobs that are currently in 'available' state (safe to update).
 *
 * The old Cyclotron DB (Rust) uses column 'state' for the status enum.
 * Production ghost runs are in the old DB.
 */
export function generateCleanupSQL(ghostRunIds: string[]): string {
    if (ghostRunIds.length === 0) {
        return '-- No ghost runs to clean up'
    }

    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
    const invalid = ghostRunIds.filter((id) => !uuidRegex.test(id))
    if (invalid.length > 0) {
        throw new Error(`Non-UUID ghost run IDs detected, refusing to generate SQL: ${invalid.slice(0, 5).join(', ')}`)
    }

    // Batch into chunks of 1000 to avoid overly large IN clauses
    const chunks: string[][] = []
    for (let i = 0; i < ghostRunIds.length; i += 1000) {
        chunks.push(ghostRunIds.slice(i, i + 1000))
    }

    let sql = `-- Ghost run cleanup: mark duplicate workflow runs as completed
-- Generated by cleanup-ghost-runs script
-- Total ghost runs: ${ghostRunIds.length}
-- Batched into ${chunks.length} statements of up to 1000 IDs each
--
-- IMPORTANT: Only updates jobs in 'available' state (not currently running).
-- Run against the old Cyclotron DB (uses 'state' column for status).
`

    for (let i = 0; i < chunks.length; i++) {
        const idList = chunks[i].map((id) => `'${id}'`).join(',\n    ')
        sql += `
-- Batch ${i + 1}/${chunks.length} (${chunks[i].length} IDs)
UPDATE cyclotron_jobs
SET state = 'completed',
    lock_id = NULL,
    last_heartbeat = NULL,
    last_transition = NOW(),
    transition_count = transition_count + 1
WHERE id IN (
    ${idList}
)
AND state = 'available';
`
    }

    return sql
}

/**
 * Parses a CSV string into LogEntry objects.
 * Handles quoted fields with commas.
 */
export function parseCSV(csv: string): LogEntry[] {
    const lines = csv.trim().split('\n')
    const header = lines[0]
    if (!header) {
        return []
    }

    const expectedColumns = ['team_id', 'run_id', 'workflow_id', 'message', 'timestamp']
    const headerColumns = header.split(',').map((h) => h.trim().toLowerCase())
    for (const col of expectedColumns) {
        if (!headerColumns.includes(col)) {
            throw new Error(`CSV header missing required column '${col}'. Found: ${headerColumns.join(', ')}`)
        }
    }

    const colIdx = Object.fromEntries(expectedColumns.map((col) => [col, headerColumns.indexOf(col)])) as Record<
        string,
        number
    >

    const entries: LogEntry[] = []

    for (let i = 1; i < lines.length; i++) {
        const line = lines[i]
        if (!line.trim()) {
            continue
        }

        // Simple CSV parsing: split by comma but respect quoted fields
        const fields: string[] = []
        let current = ''
        let inQuotes = false

        for (const char of line) {
            if (char === '"') {
                inQuotes = !inQuotes
            } else if (char === ',' && !inQuotes) {
                fields.push(current.trim())
                current = ''
            } else {
                current += char
            }
        }
        fields.push(current.trim())

        if (fields.length >= expectedColumns.length) {
            entries.push({
                team_id: fields[colIdx['team_id']].replace(/,/g, ''),
                run_id: fields[colIdx['run_id']],
                workflow_id: fields[colIdx['workflow_id']],
                message: fields[colIdx['message']],
                timestamp: fields[colIdx['timestamp']],
            })
        }
    }

    return entries
}

/**
 * Main cleanup function. Takes a CSV file path and outputs cleanup SQL.
 */
export function processCleanup(
    csvPath: string,
    filterTeamIds?: number[]
): {
    results: GhostRunResult[]
    allGhostRunIds: string[]
    sql: string
    summary: string
} {
    const csv = fs.readFileSync(csvPath, 'utf-8')
    let entries = parseCSV(csv)
    if (filterTeamIds?.length) {
        const teamSet = new Set(filterTeamIds.map(String))
        entries = entries.filter((e) => teamSet.has(e.team_id))
    }
    const results = identifyGhostRuns(entries)

    const allGhostRunIds = results.flatMap((r) => r.ghostRunIds)

    // Summary per team
    const teamSummary = new Map<string, { ghostRuns: number; affectedEvents: number }>()
    for (const result of results) {
        const existing = teamSummary.get(result.teamId) || { ghostRuns: 0, affectedEvents: 0 }
        existing.ghostRuns += result.ghostRunIds.length
        existing.affectedEvents += 1
        teamSummary.set(result.teamId, existing)
    }

    let summary = `Ghost Run Cleanup Summary\n`
    summary += `========================\n`
    summary += `Total ghost runs: ${allGhostRunIds.length}\n`
    summary += `Total affected events: ${results.length}\n`
    summary += `Total affected teams: ${teamSummary.size}\n\n`
    summary += `Per team:\n`

    for (const [teamId, stats] of teamSummary) {
        summary += `  Team ${teamId}: ${stats.ghostRuns} ghost runs across ${stats.affectedEvents} events\n`
    }

    const sql = generateCleanupSQL(allGhostRunIds)

    return { results, allGhostRunIds, sql, summary }
}

// CLI entrypoint
if (require.main === module) {
    const args = process.argv.slice(2)
    const dryRun = args.includes('--dry-run')
    const teamsIdx = args.indexOf('--teams')
    const teamIds = teamsIdx !== -1 ? args[teamsIdx + 1]?.split(',').map(Number) : undefined
    const csvPath = args.find((a) => !a.startsWith('--') && !(teamsIdx !== -1 && a === args[teamsIdx + 1]))

    if (!csvPath) {
        console.log('Usage: npx ts-node cleanup-ghost-runs.ts <csv-file> [--dry-run] [--teams <ids>]')
        console.log('')
        console.log('Options:')
        console.log('  --dry-run           Print summary only, do not write SQL files')
        console.log('  --teams 1,2,3       Only process specific team IDs from the CSV')
        console.log('')
        console.log('Step 1: Run the ClickHouse query to get the data (all teams):')
        console.log(getClickHouseQuery())
        console.log('')
        console.log('  Or for specific teams: pass team IDs to getClickHouseQuery([team1, team2])')
        console.log('')
        console.log('Step 2: Save the result as CSV and run this script with the path')
        process.exit(1)
    }

    const { summary, sql, allGhostRunIds } = processCleanup(csvPath, teamIds)

    console.log(summary)
    console.log('')

    if (dryRun) {
        console.log('Dry run - no files written.')
        process.exit(0)
    }

    // Write SQL to file
    const sqlPath = path.join(path.dirname(csvPath), 'ghost-run-cleanup.sql')
    fs.writeFileSync(sqlPath, sql)
    console.log(`SQL written to: ${sqlPath}`)

    // Write ghost IDs to file
    const idsPath = path.join(path.dirname(csvPath), 'ghost-run-ids.txt')
    fs.writeFileSync(idsPath, allGhostRunIds.join('\n'))
    console.log(`Ghost run IDs written to: ${idsPath}`)
}
