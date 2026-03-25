import { mkdtempSync, readFileSync } from 'fs'
import { tmpdir } from 'os'
import path from 'path'
import { expect, test } from 'vitest'

import { statusEvent } from '../events'
import { HogbotLogWriter } from '../log-writer'

test('log writer routes admin and research events to the right appenders', async () => {
    const calls: { admin: number; research: number } = { admin: 0, research: 0 }
    const localLogDir = mkdtempSync(path.join(tmpdir(), 'hogbot-log-writer-'))
    const localLogPath = path.join(localLogDir, 'hogbox-server.log')
    const client = {
        appendAdminLog: async () => {
            calls.admin += 1
        },
        appendResearchLog: async () => {
            calls.research += 1
        },
    } as never

    const writer = new HogbotLogWriter(
        client,
        () => {
            throw new Error('unexpected fatal')
        },
        localLogPath
    )

    writer.append('admin', statusEvent('admin', 1, 'running'))
    writer.append('research', statusEvent('research', 1, 'completed', { signalId: 'sig-1' }), 'sig-1')
    await writer.flushAll()

    expect(calls.admin).toBe(1)
    expect(calls.research).toBe(1)

    const logLines = readFileSync(localLogPath, 'utf-8')
        .trim()
        .split('\n')
        .map((line) => JSON.parse(line))

    expect(logLines).toHaveLength(2)
    expect(logLines[0].notification.method).toBe('_hogbot/status')
    expect(logLines[0].notification.params.scope).toBe('admin')
    expect(logLines[1].notification.method).toBe('_hogbot/status')
    expect(logLines[1].notification.params.scope).toBe('research')
    expect(logLines[1].notification.params.signal_id).toBe('sig-1')
})
