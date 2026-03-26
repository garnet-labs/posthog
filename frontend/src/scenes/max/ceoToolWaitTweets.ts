/**
 * Short interstitial lines for voice mode while tools run (James / PostHog flavor).
 * Played as TTS after tool-call narration so the user isn't in silence.
 */
export const CEO_TOOL_WAIT_TWEETS: readonly string[] = [
    "Walter White says he's been using Claude to optimize pricing and narcotics recipes in his lab",
    '110-year-old Turkish grandma shares her secret to a long life: "i never once used Microsoft Teams"',
    'ever since i was a kid, i knew i wanted to book a quick 5-minute demo to learn more about your agentic AI platform that saves most customers 90 minutes a day in manual tasks',
    '10 years ago, you could raise $1 million, hire a cracked team from FAANG, spend months building a product, and still get 0 customers. now, all i have to do is ask Claude to build 25 startups that all have 0 customers',
]

/**
 * Full line for ElevenLabs: casual transition + original tweet (tweet body unchanged).
 * `index` / `total` describe this batch only (0-based index, number of clips).
 */
export function waitFillClipTtsText(tweet: string, index: number, total: number): string {
    if (total <= 0) {
        return tweet
    }
    if (total === 1) {
        return `While we wait, let me share this with you. ${tweet}`
    }

    const isFirst = index === 0
    const isLast = index === total - 1

    if (isFirst) {
        return `This'll take a sec — in the meantime, ${tweet}`
    }
    if (isLast) {
        return `One more while we're at it. ${tweet}`
    }
    return `Oh and also, ${tweet}`
}

/** Pick up to `count` unique random lines for wait-fill TTS. */
export function pickRandomWaitFillTweets(count: number): string[] {
    const pool = [...CEO_TOOL_WAIT_TWEETS]
    for (let i = pool.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[pool[i], pool[j]] = [pool[j], pool[i]]
    }
    return pool.slice(0, Math.min(count, pool.length))
}
