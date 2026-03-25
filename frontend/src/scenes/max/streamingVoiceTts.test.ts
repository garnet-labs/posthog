import { commonPrefixLength, consumeSpeakableSegmentsFromDelta } from './streamingVoiceTts'

describe('consumeSpeakableSegmentsFromDelta', () => {
    it('waits for sentence end when not final', () => {
        const { segments, consumed } = consumeSpeakableSegmentsFromDelta('Hello wor', false)
        expect(segments).toEqual([])
        expect(consumed).toBe(0)
    })

    it('emits one segment at sentence boundary', () => {
        const { segments, consumed } = consumeSpeakableSegmentsFromDelta('Hello world. Next', false)
        expect(segments).toEqual(['Hello world.'])
        expect(consumed).toBeGreaterThan(0)
    })

    it('flushes remainder when final without punctuation', () => {
        const { segments, consumed } = consumeSpeakableSegmentsFromDelta('Hello wor', true)
        expect(segments).toEqual(['Hello wor'])
        expect(consumed).toBe(9)
    })

    it('consumes full delta when final with multiple sentences', () => {
        const { segments, consumed } = consumeSpeakableSegmentsFromDelta('A. B.', true)
        expect(segments.length).toBeGreaterThanOrEqual(1)
        expect(consumed).toBe(5)
    })

    it('forces a segment while streaming without punctuation after enough characters', () => {
        const long = 'word '.repeat(90)
        const { segments, consumed } = consumeSpeakableSegmentsFromDelta(long, false)
        expect(segments.length).toBeGreaterThanOrEqual(1)
        expect(consumed).toBeGreaterThan(0)
    })
})

describe('commonPrefixLength', () => {
    it('returns full length when one string extends the other', () => {
        expect(commonPrefixLength('Hello', 'Hello world')).toBe(5)
    })

    it('returns divergence index when prefixes differ', () => {
        expect(commonPrefixLength('Hello world', 'Hello there')).toBe(6)
    })
})
