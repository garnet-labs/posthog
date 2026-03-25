import { humanizeToolName, sentenceForToolNames } from './toolCallSpeech'

describe('toolCallSpeech', () => {
    it('humanizes snake_case', () => {
        expect(humanizeToolName('search_session_recordings')).toBe('search session recordings')
    })

    it('builds a single-tool sentence', () => {
        expect(sentenceForToolNames(['fix_hogql_query'])).toBe("I'm using fix hogql query.")
    })

    it('builds a multi-tool sentence', () => {
        expect(sentenceForToolNames(['a', 'b'])).toBe("I'm using a and b.")
    })

    it('returns null for empty', () => {
        expect(sentenceForToolNames([])).toBeNull()
    })
})
