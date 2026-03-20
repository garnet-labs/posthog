import { DateTime } from 'luxon'

import { LogEntry } from './types'
import { buildSurveyGlobals, fixLogDeduplication, gzipObject, sanitizeLogMessage, unGzipObject } from './utils'

describe('Utils', () => {
    describe('gzip compressions', () => {
        it("should compress and decompress a string using gzip's sync functions", async () => {
            const input = { foo: 'bar', foo2: 'bar' }
            const compressed = await gzipObject(input)
            expect(compressed).toHaveLength(52)
            const decompressed = await unGzipObject(compressed)
            expect(decompressed).toEqual(input)
        })
    })
    describe('fixLogDeduplication', () => {
        const commonProps: Omit<LogEntry, 'timestamp' | 'message'> = {
            team_id: 1,
            log_source: 'hog_function',
            log_source_id: 'hog-1',
            instance_id: 'inv-1',
            level: 'info' as const,
        }
        const startTime = DateTime.fromMillis(1620000000000)
        const example: LogEntry[] = [
            { ...commonProps, timestamp: startTime.plus(2), message: 'Third log message' },
            { ...commonProps, timestamp: startTime, message: 'First log message' },
            { ...commonProps, timestamp: startTime.plus(1), message: 'Second log message' },
            { ...commonProps, timestamp: startTime.plus(2), message: 'Duplicate log message' },
        ]
        it('should add the relevant info to the logs', () => {
            const prepared = fixLogDeduplication(example)
            expect(prepared).toMatchInlineSnapshot(
                `
                [
                  {
                    "instance_id": "inv-1",
                    "level": "info",
                    "log_source": "hog_function",
                    "log_source_id": "hog-1",
                    "message": "First log message",
                    "team_id": 1,
                    "timestamp": "2021-05-03 00:00:00.000",
                  },
                  {
                    "instance_id": "inv-1",
                    "level": "info",
                    "log_source": "hog_function",
                    "log_source_id": "hog-1",
                    "message": "Second log message",
                    "team_id": 1,
                    "timestamp": "2021-05-03 00:00:00.001",
                  },
                  {
                    "instance_id": "inv-1",
                    "level": "info",
                    "log_source": "hog_function",
                    "log_source_id": "hog-1",
                    "message": "Third log message",
                    "team_id": 1,
                    "timestamp": "2021-05-03 00:00:00.002",
                  },
                  {
                    "instance_id": "inv-1",
                    "level": "info",
                    "log_source": "hog_function",
                    "log_source_id": "hog-1",
                    "message": "Duplicate log message",
                    "team_id": 1,
                    "timestamp": "2021-05-03 00:00:00.003",
                  },
                ]
            `
            )
        })
    })
    describe('buildSurveyGlobals', () => {
        it('should map UUID-keyed responses to numeric indices using $survey_questions', () => {
            const result = buildSurveyGlobals({
                $survey_id: 'survey-uuid-123',
                $survey_questions: [
                    { id: '4e28cbea-f2a2-4730-a220-41c661a61316', question: 'How do you like it?', type: 'open' },
                    { id: 'b1c2d3e4-f5a6-7890-abcd-ef1234567890', question: 'Rate us', type: 'rating' },
                ],
                '$survey_response_4e28cbea-f2a2-4730-a220-41c661a61316': 'Great product!',
                '$survey_response_b1c2d3e4-f5a6-7890-abcd-ef1234567890': '5',
            })
            expect(result).toEqual({
                id: 'survey-uuid-123',
                response: 'Great product!',
                responses: {
                    '0': 'Great product!',
                    '1': '5',
                },
            })
        })

        it('should handle single question with UUID-keyed response', () => {
            const result = buildSurveyGlobals({
                $survey_id: 'survey-uuid-123',
                $survey_questions: [
                    { id: '4e28cbea-f2a2-4730-a220-41c661a61316', question: 'How do you like it?', type: 'open' },
                ],
                '$survey_response_4e28cbea-f2a2-4730-a220-41c661a61316': 'Great product!',
            })
            expect(result).toEqual({
                id: 'survey-uuid-123',
                response: 'Great product!',
                responses: { '0': 'Great product!' },
            })
        })

        it('should fall back to legacy index-based keys', () => {
            const result = buildSurveyGlobals({
                $survey_id: 'survey-uuid-123',
                $survey_response: 'Great product!',
                $survey_response_1: '5',
                $survey_response_2: 'More features',
            })
            expect(result).toEqual({
                id: 'survey-uuid-123',
                response: 'Great product!',
                responses: {
                    '0': 'Great product!',
                    '1': '5',
                    '2': 'More features',
                },
            })
        })

        it('should prefer UUID-keyed response over index-based when $survey_questions is present', () => {
            const result = buildSurveyGlobals({
                $survey_id: 'survey-uuid-123',
                $survey_questions: [{ id: 'q-uuid-1', question: 'Q1', type: 'open' }],
                '$survey_response_q-uuid-1': 'UUID response',
                $survey_response: 'Index response',
            })
            expect(result).toEqual({
                id: 'survey-uuid-123',
                response: 'UUID response',
                responses: { '0': 'UUID response' },
            })
        })

        it('should handle missing survey ID', () => {
            const result = buildSurveyGlobals({
                $survey_response: 'Some response',
            })
            expect(result).toEqual({
                id: '',
                response: 'Some response',
                responses: { '0': 'Some response' },
            })
        })

        it('should handle no responses', () => {
            const result = buildSurveyGlobals({
                $survey_id: 'survey-uuid-123',
            })
            expect(result).toEqual({
                id: 'survey-uuid-123',
                response: '',
                responses: {},
            })
        })

        it('should handle array responses (multiple choice)', () => {
            const result = buildSurveyGlobals({
                $survey_id: 'survey-uuid-123',
                $survey_questions: [{ id: 'q1', question: 'Pick options', type: 'multiple_choice' }],
                $survey_response_q1: ['Option A', 'Option B'],
            })
            expect(result).toEqual({
                id: 'survey-uuid-123',
                response: ['Option A', 'Option B'],
                responses: { '0': ['Option A', 'Option B'] },
            })
        })

        it('should not include non-response survey properties', () => {
            const result = buildSurveyGlobals({
                $survey_id: 'survey-uuid-123',
                $survey_questions: [{ id: 'q1', question: 'Q1', type: 'open' }],
                $survey_response_q1: 'Great!',
                $survey_completed: true,
                $survey_submission_id: 'sub-123',
                $current_url: 'https://example.com',
            })
            expect(result).toEqual({
                id: 'survey-uuid-123',
                response: 'Great!',
                responses: { '0': 'Great!' },
            })
        })
    })

    describe('sanitizeLogMessage', () => {
        it('should sanitize the log message', () => {
            const message = sanitizeLogMessage(['test', 'test2'])
            expect(message).toBe('test, test2')
        })
        it('should sanitize the log message with a sensitive value', () => {
            const message = sanitizeLogMessage(['test', 'test2'], ['test2'])
            expect(message).toBe('test, ***REDACTED***')
        })
        it('should sanitize a range of values types', () => {
            const message = sanitizeLogMessage(['test', 'test2', 1, true, false, null, undefined, { test: 'test' }])
            expect(message).toMatchInlineSnapshot(`"test, test2, 1, true, false, null, , {"test":"test"}"`)
        })
        it('should truncate the log message if it is too long', () => {
            const veryLongMessage = Array(10000).fill('test').join('')
            const message = sanitizeLogMessage([veryLongMessage], [], 10)
            expect(message).toMatchInlineSnapshot(`"testtestte... (truncated)"`)
        })
        it('should not truncate through Unicode surrogate pairs', () => {
            const emoji = '🚀🎉💯🔥'
            const longMessage = emoji + Array(1000).fill('a').join('')
            const message = sanitizeLogMessage([longMessage], [], 10)
            expect(message).not.toMatch(/[\uD800-\uDBFF]$/)
            expect(message).not.toMatch(/[\uDC00-\uDFFF]$/)
            expect(message).toMatch(/\.\.\. \(truncated\)$/)
        })
        it('should handle truncation at exact surrogate pair boundary', () => {
            expect(sanitizeLogMessage(['\ud83c\udf82'], [], 1)).not.toContain('\ud83c')
            expect(sanitizeLogMessage(['🚀🚀🚀🚀🚀'], [], 2)).toMatchInlineSnapshot(`"🚀... (truncated)"`)
            expect(sanitizeLogMessage(['🚀🚀🚀🚀🚀'], [], 3)).toMatchInlineSnapshot(`"🚀... (truncated)"`)
            expect(sanitizeLogMessage(['🚀🚀🚀🚀🚀'], [], 4)).toMatchInlineSnapshot(`"🚀🚀... (truncated)"`)
        })
    })
})
