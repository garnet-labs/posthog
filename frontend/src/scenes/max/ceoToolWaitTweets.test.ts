import { CEO_TOOL_WAIT_TWEETS, waitFillClipTtsText } from './ceoToolWaitTweets'

describe('ceoToolWaitTweets', () => {
    const tweet = CEO_TOOL_WAIT_TWEETS[0]

    it('waitFillClipTtsText keeps tweet body intact and adds concise wrap for a single clip', () => {
        const line = waitFillClipTtsText(tweet, 0, 1)
        expect(line).toContain(tweet)
        expect(line).toContain('let me share this with you')
    })

    it('first of two uses an opener; last uses a different transition', () => {
        const first = waitFillClipTtsText(tweet, 0, 2)
        const last = waitFillClipTtsText(tweet, 1, 2)
        expect(first).toContain(tweet)
        expect(last).toContain(tweet)
        expect(first).toContain('in the meantime')
        expect(last).toContain("while we're at it")
        expect(first).not.toBe(last)
    })

    it('middle clip of three uses another transition', () => {
        const mid = waitFillClipTtsText(tweet, 1, 3)
        expect(mid).toContain('Oh and also')
    })
})
