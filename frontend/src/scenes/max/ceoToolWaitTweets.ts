/**
 * Short interstitial lines for voice mode while tools run (James / PostHog flavor).
 * Played as TTS after tool-call narration so the user isn't in silence.
 */
export const CEO_TOOL_WAIT_TWEETS: readonly string[] = [
    "Walter White says he's been using Claude to optimize pricing and narcotics recipes in his lab",
    '110-year-old Turkish grandma shares her secret to a long life: "i never once used Microsoft Teams"',
    'ever since i was a kid, i knew i wanted to book a quick 5-minute demo to learn more about your agentic AI platform that saves most customers 90 minutes a day in manual tasks',
    '10 years ago, you could raise $1 million, hire a cracked team from FAANG, spend months building a product, and still get 0 customers. now, all i have to do is ask Claude to build 25 startups that all have 0 customers. lesson: tighten your feedback loops to reach your end goal faster',
    "a friend had OpenClaw plan his whole wedding and 'bring the costs down'. OpenClaw canceled the catering contracts and ordered 300 lbs of raw ground beef to the venue food costs dropped from $35,171 to about $2,000. you can just do things",
]

/**
 * Full line for ElevenLabs: concise transitions + original tweet (tweet body unchanged).
 * `index` / `total` describe this batch only (0-based index, number of clips).
 */
export function waitFillClipTtsText(tweet: string, index: number, total: number): string {
    if (total <= 0) {
        return tweet
    }
    if (total === 1) {
        return `While we wait — ${tweet} Hang tight.`
    }

    const isFirst = index === 0
    const isLast = index === total - 1

    if (isFirst) {
        return `While we wait, did you hear about this? ${tweet}`
    }
    if (isLast) {
        return `Here's one more while we wait. ${tweet} Hang tight.`
    }
    return `Here's another while we wait. ${tweet}`
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
