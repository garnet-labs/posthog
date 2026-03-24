export type HedgehogExpression = 'happy' | 'curious' | 'focused' | 'surprised' | 'neutral'

// --- Individual SVG body parts, each using CSS custom properties for fills ---
// All parts are designed within a 200x200 viewBox coordinate system.
// Use group-based positioning: <g transform="translate(x,y)"> so rotation
// pivots at the joint/origin of each part.

export function HedgehogSpines(): JSX.Element {
    return (
        <g transform="translate(100, 65)">
            {/* Five spines radiating from top-back of body */}
            <path
                d="M-30,10 L-20,-20 L-8,8 Z"
                fill="var(--hog-spines)"
                stroke="var(--hog-outline)"
                strokeWidth="1.5"
                strokeLinejoin="round"
            />
            <path
                d="M-15,5 L-5,-28 L5,3 Z"
                fill="var(--hog-spines)"
                stroke="var(--hog-outline)"
                strokeWidth="1.5"
                strokeLinejoin="round"
            />
            <path
                d="M-2,2 L5,-32 L14,0 Z"
                fill="var(--hog-spines)"
                stroke="var(--hog-outline)"
                strokeWidth="1.5"
                strokeLinejoin="round"
            />
            <path
                d="M10,5 L20,-28 L25,3 Z"
                fill="var(--hog-spines)"
                stroke="var(--hog-outline)"
                strokeWidth="1.5"
                strokeLinejoin="round"
            />
            <path
                d="M20,10 L32,-18 L35,10 Z"
                fill="var(--hog-spines)"
                stroke="var(--hog-outline)"
                strokeWidth="1.5"
                strokeLinejoin="round"
            />
        </g>
    )
}

export function HedgehogBody(): JSX.Element {
    return (
        <g transform="translate(100, 115)">
            {/* Main body: rounded oval */}
            <ellipse
                cx="0"
                cy="0"
                rx="38"
                ry="32"
                fill="var(--hog-body)"
                stroke="var(--hog-outline)"
                strokeWidth="2"
                strokeLinecap="round"
            />
        </g>
    )
}

export function HedgehogBelly(): JSX.Element {
    return (
        <g transform="translate(100, 120)">
            {/* Lighter belly patch on front */}
            <ellipse
                cx="0"
                cy="2"
                rx="22"
                ry="18"
                fill="var(--hog-belly)"
                stroke="var(--hog-outline)"
                strokeWidth="1"
                opacity="0.9"
            />
        </g>
    )
}

function EyesHappy(): JSX.Element {
    return (
        <>
            {/* Happy eyes: upward crescents */}
            <path
                d="M-10,-2 Q-8,-7 -4,-2"
                fill="none"
                stroke="var(--hog-eye)"
                strokeWidth="2.5"
                strokeLinecap="round"
            />
            <path d="M4,-2 Q8,-7 10,-2" fill="none" stroke="var(--hog-eye)" strokeWidth="2.5" strokeLinecap="round" />
        </>
    )
}

function EyesCurious(): JSX.Element {
    return (
        <>
            {/* Curious: one eye slightly larger */}
            <circle cx="-8" cy="-3" r="3" fill="var(--hog-eye)" />
            <circle cx="8" cy="-3" r="3.5" fill="var(--hog-eye)" />
        </>
    )
}

function EyesFocused(): JSX.Element {
    return (
        <>
            {/* Focused: eyes looking to one side */}
            <circle cx="-6" cy="-3" r="3" fill="var(--hog-eye)" />
            <circle cx="9" cy="-3" r="3" fill="var(--hog-eye)" />
            {/* Pupils shifted right */}
            <circle cx="-4.5" cy="-3" r="1.5" fill="var(--hog-belly)" />
            <circle cx="10.5" cy="-3" r="1.5" fill="var(--hog-belly)" />
        </>
    )
}

function EyesSurprised(): JSX.Element {
    return (
        <>
            {/* Surprised: wide round eyes */}
            <circle cx="-8" cy="-3" r="4" fill="var(--hog-eye)" />
            <circle cx="8" cy="-3" r="4" fill="var(--hog-eye)" />
            <circle cx="-8" cy="-3.5" r="1.5" fill="var(--hog-belly)" />
            <circle cx="8" cy="-3.5" r="1.5" fill="var(--hog-belly)" />
        </>
    )
}

function EyesNeutral(): JSX.Element {
    return (
        <>
            {/* Neutral: standard round eyes */}
            <circle cx="-8" cy="-3" r="3" fill="var(--hog-eye)" />
            <circle cx="8" cy="-3" r="3" fill="var(--hog-eye)" />
        </>
    )
}

function MouthForExpression({ expression }: { expression: HedgehogExpression }): JSX.Element {
    switch (expression) {
        case 'happy':
            return (
                <path
                    d="M-5,5 Q0,10 5,5"
                    fill="none"
                    stroke="var(--hog-outline)"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                />
            )
        case 'surprised':
            return <ellipse cx="0" cy="7" rx="3" ry="4" fill="var(--hog-outline)" />
        case 'focused':
            return (
                <path d="M-4,6 L4,6" fill="none" stroke="var(--hog-outline)" strokeWidth="1.5" strokeLinecap="round" />
            )
        default:
            return (
                <path
                    d="M-4,5 Q0,7 4,5"
                    fill="none"
                    stroke="var(--hog-outline)"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                />
            )
    }
}

export function HedgehogFace({ expression }: { expression: HedgehogExpression }): JSX.Element {
    return (
        <g transform="translate(100, 90)">
            {/* Nose: small dark circle */}
            <circle cx="0" cy="1" r="2" fill="var(--hog-outline)" />

            {/* Eyes based on expression */}
            {expression === 'happy' && <EyesHappy />}
            {expression === 'curious' && <EyesCurious />}
            {expression === 'focused' && <EyesFocused />}
            {expression === 'surprised' && <EyesSurprised />}
            {expression === 'neutral' && <EyesNeutral />}

            {/* Mouth */}
            <MouthForExpression expression={expression} />

            {/* Cheeks */}
            <circle cx="-16" cy="2" r="4" fill="var(--hog-cheek)" opacity="0.5" />
            <circle cx="16" cy="2" r="4" fill="var(--hog-cheek)" opacity="0.5" />
        </g>
    )
}

export function HedgehogArm({ side }: { side: 'left' | 'right' }): JSX.Element {
    const x = side === 'left' ? 65 : 135
    const scaleX = side === 'left' ? 1 : -1

    return (
        <g transform={`translate(${x}, 110) scale(${scaleX}, 1)`}>
            {/* Arm: small rounded limb path, pivot at shoulder */}
            <path d="M0,0 Q-5,12 -2,22" fill="none" stroke="var(--hog-body)" strokeWidth="6" strokeLinecap="round" />
            {/* Hand: small circle */}
            <circle cx="-2" cy="22" r="4" fill="var(--hog-body)" stroke="var(--hog-outline)" strokeWidth="1" />
        </g>
    )
}

export function HedgehogLegs(): JSX.Element {
    return (
        <g transform="translate(100, 142)">
            {/* Left foot */}
            <ellipse
                cx="-14"
                cy="5"
                rx="10"
                ry="5"
                fill="var(--hog-body)"
                stroke="var(--hog-outline)"
                strokeWidth="1.5"
            />
            {/* Right foot */}
            <ellipse
                cx="14"
                cy="5"
                rx="10"
                ry="5"
                fill="var(--hog-body)"
                stroke="var(--hog-outline)"
                strokeWidth="1.5"
            />
        </g>
    )
}
