import {
    humanizeToolName,
    reasonFromAssistantContent,
    sentenceForToolCalls,
    sentenceForToolNames,
} from './toolCallSpeech'

describe('toolCallSpeech', () => {
    it('humanizes snake_case', () => {
        expect(humanizeToolName('search_session_recordings')).toBe('search session recordings')
    })

    it('builds a single-tool sentence without reason', () => {
        expect(sentenceForToolCalls(['fix_hogql_query'])).toBe("I'm using fix hogql query.")
    })

    it('builds a multi-tool sentence without reason', () => {
        expect(sentenceForToolCalls(['a', 'b'])).toBe("I'm using a and b.")
    })

    it('includes assistant content as reason', () => {
        expect(
            sentenceForToolCalls(['run_query'], {
                assistantContent: 'Let me check that funnel for you.',
            })
        ).toBe("I'm using run query to check that funnel for you.")
    })

    it('prefers assistant reason over args', () => {
        expect(
            sentenceForToolCalls(['run_query'], {
                assistantContent: 'Pulling the numbers now.',
                toolCalls: [{ name: 'run_query', args: { query: 'SELECT 1' } }],
            })
        ).toBe("I'm using run query to pulling the numbers now.")
    })

    it('uses args when no assistant reason', () => {
        expect(
            sentenceForToolCalls(['search_docs'], {
                toolCalls: [{ name: 'search_docs', args: { query: 'retention cohorts' } }],
            })
        ).toBe("I'm using search docs to retention cohorts.")
    })

    it('returns null for empty names', () => {
        expect(sentenceForToolCalls([])).toBeNull()
    })

    it('reasonFromAssistantContent strips filler', () => {
        expect(reasonFromAssistantContent("I'll look up your insights.")).toBe('look up your insights')
    })

    it('sentenceForToolNames delegates to sentenceForToolCalls', () => {
        expect(sentenceForToolNames(['x'])).toBe("I'm using x.")
    })
})
