import { mkdtempSync, rmdirSync, symlinkSync, unlinkSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import path from 'path'
import { afterEach, expect, test } from 'vitest'

import { FilesystemError, readFilesystemFile, statFilesystemEntry } from '../filesystem'

const tempPaths: string[] = []

afterEach(() => {
    while (tempPaths.length > 0) {
        const target = tempPaths.pop()
        if (!target) {
            continue
        }
        try {
            try {
                unlinkSync(target)
            } catch {
                ;(rmdirSync as unknown as (path: string, options?: unknown) => void)(target, { recursive: true })
            }
        } catch {
            // Ignore cleanup errors in tests.
        }
    }
})

test('statFilesystemEntry rejects path traversal', async () => {
    const workspace = mkdtempSync(path.join(tmpdir(), 'hogbot-fs-'))
    tempPaths.push(workspace)

    await expect(statFilesystemEntry(workspace, '/../secret')).rejects.toBeInstanceOf(FilesystemError)
})

test('readFilesystemFile reads workspace files', async () => {
    const workspace = mkdtempSync(path.join(tmpdir(), 'hogbot-fs-'))
    tempPaths.push(workspace)
    writeFileSync(path.join(workspace, 'test.txt'), 'hello')

    const response = await readFilesystemFile(workspace, '/test.txt')
    expect(response.content).toBe('hello')
    expect(response.truncated).toBe(false)
})

test('symlink escaping the workspace is rejected', async () => {
    const workspace = mkdtempSync(path.join(tmpdir(), 'hogbot-fs-'))
    const outside = mkdtempSync(path.join(tmpdir(), 'hogbot-outside-'))
    tempPaths.push(workspace, outside)

    writeFileSync(path.join(outside, 'secret.txt'), 'nope')
    symlinkSync(path.join(outside, 'secret.txt'), path.join(workspace, 'link.txt'))

    await expect(readFilesystemFile(workspace, '/link.txt')).rejects.toBeInstanceOf(FilesystemError)
})
