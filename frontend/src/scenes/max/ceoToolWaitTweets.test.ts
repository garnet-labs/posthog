import { CEO_TOOL_WAIT_TWEETS, waitFillClipTtsText } from './ceoToolWaitTweets'

describe('ceoToolWaitTweets', () => {
    const tweet = CEO_TOOL_WAIT_TWEETS[0]

    it('waitFillClipTtsText keeps tweet body intact and adds concise wrap for a single clip', () => {
        const line = waitFillClipTtsText(tweet, 0, 1)
        expect(line.includes(tweet)).toBe(true)
        expect(line.startsWith('While we wait')).toBe(true)
        expect(line.endsWith('Hang tight.')).toBe(true)
    })

    it('first of two uses an opener; last uses handoff and closing', () => {
        const first = waitFillClipTtsText(tweet, 0, 2)
        const last = waitFillClipTtsText(tweet, 1, 2)
        expect(first).toContain('did you hear')
        expect(last).toContain("Here's one more while we wait")
        expect(last.endsWith('Hang tight.')).toBe(true)
        expect(first).not.toBe(last)
    })

    it('middle clip of three uses another transition', () => {
        const mid = waitFillClipTtsText(tweet, 1, 3)
        expect(mid).toContain("Here's another while we wait")
    })
})
