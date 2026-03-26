import { extractActionId, extractEventId, generateCleanupSQL, identifyGhostRuns, parseCSV } from './cleanup-ghost-runs'

describe('cleanup-ghost-runs', () => {
    describe('extractEventId', () => {
        it('extracts event ID from a Resuming workflow message', () => {
            const message =
                'Resuming workflow execution at [Action:action_conditional_branch_c0daca89] on [Event:019d035d-56b0-7f2d-a109-f7bfef12c591|$pageview|2026-03-18T23:52:23.085Z]'
            expect(extractEventId(message)).toBe('019d035d-56b0-7f2d-a109-f7bfef12c591')
        })

        it('returns null for messages without an event', () => {
            expect(extractEventId('Workflow completed')).toBeNull()
        })

        it('handles event IDs with different formats', () => {
            const message =
                'Resuming workflow execution at [Action:abc] on [Event:1bf394c3-9aea-464e-ab7a-0db8335bb6b2|user_signed_up|2026-03-20T11:57:25.249Z]'
            expect(extractEventId(message)).toBe('1bf394c3-9aea-464e-ab7a-0db8335bb6b2')
        })
    })

    describe('extractActionId', () => {
        it('extracts action ID from a workflow message', () => {
            const message =
                'Resuming workflow execution at [Action:action_conditional_branch_c0daca89] on [Event:abc|test|2026-01-01]'
            expect(extractActionId(message)).toBe('action_conditional_branch_c0daca89')
        })

        it('returns null for messages without an action', () => {
            expect(extractActionId('Workflow completed')).toBeNull()
        })
    })

    describe('identifyGhostRuns', () => {
        it('identifies ghost runs when multiple runs share the same event', () => {
            const entries = [
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-1',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:52:28.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-2',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:53:05.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-3',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:53:45.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-4',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:54:25.000000',
                },
            ]

            const results = identifyGhostRuns(entries)

            expect(results).toHaveLength(1)
            expect(results[0].legitimateRunId).toBe('run-1')
            expect(results[0].ghostRunIds).toEqual(['run-2', 'run-3', 'run-4'])
            expect(results[0].totalRuns).toBe(4)
            expect(results[0].teamId).toBe('47337')
        })

        it('does not flag single runs as ghosts', () => {
            const entries = [
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-1',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:52:28.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-2',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-2|test|2026-01-01]',
                    timestamp: '2026-03-19 02:00:00.000000',
                },
            ]

            const results = identifyGhostRuns(entries)
            expect(results).toHaveLength(0)
        })

        it('handles multiple teams independently', () => {
            const entries = [
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-1a',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:52:28.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-1b',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:53:05.000000',
                },
                {
                    team_id: '281194',
                    workflow_id: 'wf-2',
                    run_id: 'run-2a',
                    message: 'Resuming workflow execution at [Action:xyz] on [Event:event-2|test|2026-01-01]',
                    timestamp: '2026-03-19 01:52:28.000000',
                },
                {
                    team_id: '281194',
                    workflow_id: 'wf-2',
                    run_id: 'run-2b',
                    message: 'Resuming workflow execution at [Action:xyz] on [Event:event-2|test|2026-01-01]',
                    timestamp: '2026-03-19 01:53:05.000000',
                },
            ]

            const results = identifyGhostRuns(entries)

            expect(results).toHaveLength(2)

            const team47337 = results.find((r) => r.teamId === '47337')!
            expect(team47337.legitimateRunId).toBe('run-1a')
            expect(team47337.ghostRunIds).toEqual(['run-1b'])

            const team281194 = results.find((r) => r.teamId === '281194')!
            expect(team281194.legitimateRunId).toBe('run-2a')
            expect(team281194.ghostRunIds).toEqual(['run-2b'])
        })

        it('keeps earliest run as legitimate regardless of input order', () => {
            const entries = [
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-late',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:54:25.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-early',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:52:28.000000',
                },
            ]

            const results = identifyGhostRuns(entries)

            expect(results[0].legitimateRunId).toBe('run-early')
            expect(results[0].ghostRunIds).toEqual(['run-late'])
        })

        it('deduplicates run IDs that appear multiple times in log entries', () => {
            const entries = [
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-1',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:52:28.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-1',
                    message: 'Resuming workflow execution at [Action:def] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:52:29.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-2',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:53:05.000000',
                },
            ]

            const results = identifyGhostRuns(entries)

            expect(results).toHaveLength(1)
            expect(results[0].legitimateRunId).toBe('run-1')
            expect(results[0].ghostRunIds).toEqual(['run-2'])
            expect(results[0].totalRuns).toBe(2)
        })

        it('handles different events for the same team correctly', () => {
            const entries = [
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-1',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-A|test|2026-01-01]',
                    timestamp: '2026-03-19 01:52:28.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-2',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-A|test|2026-01-01]',
                    timestamp: '2026-03-19 01:53:05.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-3',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-B|test|2026-01-01]',
                    timestamp: '2026-03-19 02:00:00.000000',
                },
            ]

            const results = identifyGhostRuns(entries)

            expect(results).toHaveLength(1)
            expect(results[0].eventId).toBe('event-A')
            expect(results[0].ghostRunIds).toEqual(['run-2'])
        })

        it('returns empty array for empty input', () => {
            expect(identifyGhostRuns([])).toEqual([])
        })

        it('skips entries without event IDs', () => {
            const entries = [
                {
                    team_id: '47337',
                    workflow_id: 'wf-1',
                    run_id: 'run-1',
                    message: 'Some message without event',
                    timestamp: '2026-03-19 01:52:28.000000',
                },
            ]

            expect(identifyGhostRuns(entries)).toEqual([])
        })

        it('does not flag different workflows triggered by the same event as ghosts', () => {
            const entries = [
                {
                    team_id: '47337',
                    workflow_id: 'workflow-A',
                    run_id: 'run-1',
                    message: 'Resuming workflow execution at [Action:abc] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:52:28.000000',
                },
                {
                    team_id: '47337',
                    workflow_id: 'workflow-B',
                    run_id: 'run-2',
                    message: 'Resuming workflow execution at [Action:xyz] on [Event:event-1|test|2026-01-01]',
                    timestamp: '2026-03-19 01:52:30.000000',
                },
            ]

            const results = identifyGhostRuns(entries)
            expect(results).toHaveLength(0)
        })
    })

    describe('parseCSV', () => {
        it('parses a simple CSV', () => {
            const csv = `team_id,run_id,workflow_id,message,timestamp
47337,run-1,wf-1,Resuming workflow at [Action:abc] on [Event:e1|test|2026],2026-03-19 01:00:00
47337,run-2,wf-1,Resuming workflow at [Action:abc] on [Event:e1|test|2026],2026-03-19 01:01:00`

            const entries = parseCSV(csv)

            expect(entries).toHaveLength(2)
            expect(entries[0].team_id).toBe('47337')
            expect(entries[0].run_id).toBe('run-1')
            expect(entries[0].workflow_id).toBe('wf-1')
            expect(entries[1].run_id).toBe('run-2')
        })

        it('handles quoted fields with commas', () => {
            const csv = `team_id,run_id,workflow_id,message,timestamp
"47,337",run-1,wf-1,Resuming workflow,2026-03-19 01:00:00`

            const entries = parseCSV(csv)

            expect(entries).toHaveLength(1)
            expect(entries[0].team_id).toBe('47337')
        })

        it('handles empty input', () => {
            expect(parseCSV('')).toEqual([])
        })

        it('handles header only', () => {
            expect(parseCSV('team_id,run_id,workflow_id,message,timestamp')).toEqual([])
        })
    })

    describe('generateCleanupSQL', () => {
        it('generates SQL for ghost run IDs', () => {
            const sql = generateCleanupSQL(['run-1', 'run-2', 'run-3'])

            expect(sql).toContain("'run-1'")
            expect(sql).toContain("'run-2'")
            expect(sql).toContain("'run-3'")
            expect(sql).toContain("state = 'completed'")
            expect(sql).toContain("AND state = 'available'")
            expect(sql).toContain('Total ghost runs: 3')
        })

        it('returns comment for empty input', () => {
            const sql = generateCleanupSQL([])
            expect(sql).toBe('-- No ghost runs to clean up')
        })

        it('only updates available jobs', () => {
            const sql = generateCleanupSQL(['run-1'])
            expect(sql).toContain("AND state = 'available'")
        })
    })
})
