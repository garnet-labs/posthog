import { afterEach, beforeAll, describe, expect, it } from 'vitest'

import {
    TEST_ORG_ID,
    TEST_PROJECT_ID,
    createTestClient,
    createTestContext,
    generateUniqueKey,
    parseToolResponse,
    setActiveProjectAndOrg,
    validateEnvironmentVariables,
} from '@/shared/test-utils'
import { GENERATED_TOOLS } from '@/tools/generated/batch_exports'
import type { Context } from '@/tools/types'

describe('Batch exports', { concurrent: false }, () => {
    let context: Context
    const createdExportIds: string[] = []

    const listTool = GENERATED_TOOLS['batch-exports-list']!()
    const getTool = GENERATED_TOOLS['batch-export-get']!()
    const createTool = GENERATED_TOOLS['batch-export-create']!()
    const updateTool = GENERATED_TOOLS['batch-export-update']!()
    const deleteTool = GENERATED_TOOLS['batch-export-delete']!()
    const pauseTool = GENERATED_TOOLS['batch-export-pause']!()
    const unpauseTool = GENERATED_TOOLS['batch-export-unpause']!()
    const runsListTool = GENERATED_TOOLS['batch-export-runs-list']!()

    beforeAll(async () => {
        validateEnvironmentVariables()
        const client = createTestClient()
        context = createTestContext(client)
        await setActiveProjectAndOrg(context, TEST_PROJECT_ID!, TEST_ORG_ID!)
    })

    afterEach(async () => {
        for (const id of createdExportIds) {
            try {
                await deleteTool.handler(context, { id })
            } catch {
                // best effort — export may already be deleted
            }
        }
        createdExportIds.length = 0
    })

    function makeExportParams(overrides: Record<string, unknown> = {}): Record<string, unknown> {
        return {
            name: `test-export-${generateUniqueKey('batch')}`,
            interval: 'hour',
            destination: {
                type: 'S3',
                config: {
                    bucket_name: `test-bucket-${generateUniqueKey('s3')}`,
                    region: 'us-east-1',
                    prefix: 'test/',
                    aws_access_key_id: 'test-key-id',
                    aws_secret_access_key: 'test-secret-key',
                },
            },
            paused: true,
            ...overrides,
        }
    }

    describe('batch-exports-list tool', () => {
        it('should return paginated structure', async () => {
            const result = await listTool.handler(context, {})
            const data = parseToolResponse(result)

            expect(typeof data.count).toBe('number')
            expect(Array.isArray(data.results)).toBe(true)
            expect(typeof data._posthogUrl).toBe('string')
            expect(data._posthogUrl).toContain('/batch_exports')
        })

        it('should respect the limit parameter', async () => {
            const result = await listTool.handler(context, { limit: 1 })
            const data = parseToolResponse(result)

            expect(Array.isArray(data.results)).toBe(true)
            expect(data.results.length).toBeLessThanOrEqual(1)
        })
    })

    describe('batch-export-create tool', () => {
        it('should create an S3 batch export', async () => {
            const params = makeExportParams()
            const result = await createTool.handler(context, params)
            const exportData = parseToolResponse(result)
            createdExportIds.push(exportData.id)

            expect(exportData.id).toBeTruthy()
            expect(exportData.name).toBe(params.name)
            expect(exportData.interval).toBe('hour')
            expect(exportData.paused).toBe(true)
            expect(exportData.destination.type).toBe('S3')
        })

        it('should create with daily interval', async () => {
            const params = makeExportParams({ interval: 'day' })
            const result = await createTool.handler(context, params)
            const exportData = parseToolResponse(result)
            createdExportIds.push(exportData.id)

            expect(exportData.interval).toBe('day')
        })
    })

    describe('batch-export-get tool', () => {
        it('should retrieve a specific export by ID', async () => {
            const created = await createTool.handler(context, makeExportParams())
            const createdExport = parseToolResponse(created)
            createdExportIds.push(createdExport.id)

            const result = await getTool.handler(context, { id: createdExport.id })
            const exportData = parseToolResponse(result)

            expect(exportData.id).toBe(createdExport.id)
            expect(exportData.name).toBe(createdExport.name)
            expect(exportData.destination).toBeTruthy()
        })

        it('should throw for a non-existent UUID', async () => {
            const absentId = crypto.randomUUID()
            await expect(getTool.handler(context, { id: absentId })).rejects.toThrow()
        })
    })

    describe('batch-export-update tool', () => {
        it('should update the name', async () => {
            const created = await createTool.handler(context, makeExportParams())
            const exportData = parseToolResponse(created)
            createdExportIds.push(exportData.id)

            const newName = `renamed-${generateUniqueKey('batch')}`
            const result = await updateTool.handler(context, { id: exportData.id, name: newName })
            const updated = parseToolResponse(result)

            expect(updated.name).toBe(newName)
            expect(updated.id).toBe(exportData.id)
        })

        it('should update the interval', async () => {
            const created = await createTool.handler(context, makeExportParams())
            const exportData = parseToolResponse(created)
            createdExportIds.push(exportData.id)

            const result = await updateTool.handler(context, { id: exportData.id, interval: 'day' })
            const updated = parseToolResponse(result)

            expect(updated.interval).toBe('day')
        })
    })

    describe('batch-export-runs-list tool', () => {
        it('should return runs structure for an export', async () => {
            const created = await createTool.handler(context, makeExportParams())
            const exportData = parseToolResponse(created)
            createdExportIds.push(exportData.id)

            const result = await runsListTool.handler(context, { batch_export_id: exportData.id })
            const data = parseToolResponse(result)

            expect(Array.isArray(data.results)).toBe(true)
            expect(typeof data._posthogUrl).toBe('string')
        })
    })

    describe('batch-export-delete tool', () => {
        it('should delete an export', async () => {
            const created = await createTool.handler(context, makeExportParams())
            const exportData = parseToolResponse(created)

            await deleteTool.handler(context, { id: exportData.id })
            await expect(getTool.handler(context, { id: exportData.id })).rejects.toThrow()
        })
    })

    describe('batch-export-pause/unpause tools', () => {
        it('should pause a batch export', async () => {
            const created = await createTool.handler(context, makeExportParams({ paused: false }))
            const exportData = parseToolResponse(created)
            createdExportIds.push(exportData.id)

            await pauseTool.handler(context, { id: exportData.id })

            const result = await getTool.handler(context, { id: exportData.id })
            const updated = parseToolResponse(result)
            expect(updated.paused).toBe(true)
        })

        it('should unpause a paused batch export', async () => {
            const created = await createTool.handler(context, makeExportParams({ paused: true }))
            const exportData = parseToolResponse(created)
            createdExportIds.push(exportData.id)

            await unpauseTool.handler(context, { id: exportData.id })

            const result = await getTool.handler(context, { id: exportData.id })
            const updated = parseToolResponse(result)
            expect(updated.paused).toBe(false)
        })
    })

    describe('Batch export workflow', () => {
        it('should support a full create → get → update → list runs → delete lifecycle', async () => {
            const name = `workflow-export-${generateUniqueKey('lifecycle')}`

            // Create
            const createResult = await createTool.handler(context, makeExportParams({ name }))
            const created = parseToolResponse(createResult)
            expect(created.id).toBeTruthy()
            expect(created.name).toBe(name)

            // Get
            const getResult = await getTool.handler(context, { id: created.id })
            const retrieved = parseToolResponse(getResult)
            expect(retrieved.id).toBe(created.id)

            // Update
            const updatedName = `${name}-updated`
            const updateResult = await updateTool.handler(context, { id: created.id, name: updatedName })
            const updated = parseToolResponse(updateResult)
            expect(updated.name).toBe(updatedName)

            // List runs
            const runsResult = await runsListTool.handler(context, { batch_export_id: created.id })
            const runs = parseToolResponse(runsResult)
            expect(Array.isArray(runs.results)).toBe(true)

            // Delete
            await deleteTool.handler(context, { id: created.id })
            await expect(getTool.handler(context, { id: created.id })).rejects.toThrow()
        })

        it('should appear in list results after creation', async () => {
            const name = `list-check-${generateUniqueKey('appear')}`

            const createResult = await createTool.handler(context, makeExportParams({ name }))
            const created = parseToolResponse(createResult)
            createdExportIds.push(created.id)

            const listResult = await listTool.handler(context, {})
            const data = parseToolResponse(listResult)

            const found = data.results.find((e: any) => e.id === created.id)
            expect(found).toBeTruthy()
            expect(found.name).toBe(name)
        })
    })
})
