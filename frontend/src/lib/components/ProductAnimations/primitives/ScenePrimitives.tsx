/**
 * Reusable SVG scene elements for product animations.
 * All elements are designed for a 200x200 viewBox and use CSS custom properties.
 */

// --- Chart elements ---

export function TrendLine({ color = 'var(--hog-body)' }: { color?: string }): JSX.Element {
    return (
        <path
            d="M20,160 Q50,150 70,130 T110,90 T150,50 T180,30"
            fill="none"
            stroke={color}
            strokeWidth="3"
            strokeLinecap="round"
        />
    )
}

export function DataPoints({ color = 'var(--hog-body)' }: { color?: string }): JSX.Element {
    return (
        <g>
            <circle cx="70" cy="130" r="4" fill={color} />
            <circle cx="110" cy="90" r="4" fill={color} />
            <circle cx="150" cy="50" r="4" fill={color} />
            <circle cx="180" cy="30" r="4" fill={color} />
        </g>
    )
}

export function ChartGrid(): JSX.Element {
    return (
        <g opacity="0.15">
            <line x1="20" y1="160" x2="190" y2="160" stroke="var(--hog-outline)" strokeWidth="1" />
            <line x1="20" y1="130" x2="190" y2="130" stroke="var(--hog-outline)" strokeWidth="0.5" />
            <line x1="20" y1="100" x2="190" y2="100" stroke="var(--hog-outline)" strokeWidth="0.5" />
            <line x1="20" y1="70" x2="190" y2="70" stroke="var(--hog-outline)" strokeWidth="0.5" />
            <line x1="20" y1="40" x2="190" y2="40" stroke="var(--hog-outline)" strokeWidth="0.5" />
        </g>
    )
}

export function BarChart(): JSX.Element {
    return (
        <g>
            <rect x="30" y="120" width="16" height="40" rx="2" fill="var(--hog-body)" opacity="0.7" />
            <rect x="55" y="90" width="16" height="70" rx="2" fill="var(--hog-body)" opacity="0.8" />
            <rect x="80" y="105" width="16" height="55" rx="2" fill="var(--hog-body)" opacity="0.7" />
            <rect x="105" y="70" width="16" height="90" rx="2" fill="var(--hog-body)" opacity="0.9" />
            <rect x="130" y="85" width="16" height="75" rx="2" fill="var(--hog-body)" opacity="0.8" />
        </g>
    )
}

// --- UI elements ---

export function MiniScreen({ x = 0, y = 0 }: { x?: number; y?: number }): JSX.Element {
    return (
        <g transform={`translate(${x}, ${y})`}>
            <rect
                x="0"
                y="0"
                width="80"
                height="55"
                rx="4"
                fill="var(--hog-belly)"
                stroke="var(--hog-outline)"
                strokeWidth="1.5"
            />
            {/* Title bar */}
            <rect x="0" y="0" width="80" height="10" rx="4" fill="var(--hog-outline)" opacity="0.15" />
            <circle cx="8" cy="5" r="2" fill="var(--hog-cheek)" opacity="0.6" />
            <circle cx="15" cy="5" r="2" fill="var(--hog-body)" opacity="0.6" />
            <circle
                cx="22"
                cy="5"
                r="2"
                fill="var(--hog-belly)"
                stroke="var(--hog-outline)"
                strokeWidth="0.5"
                opacity="0.6"
            />
            {/* Content lines */}
            <rect x="6" y="16" width="40" height="3" rx="1" fill="var(--hog-outline)" opacity="0.2" />
            <rect x="6" y="23" width="55" height="3" rx="1" fill="var(--hog-outline)" opacity="0.15" />
            <rect x="6" y="30" width="35" height="3" rx="1" fill="var(--hog-outline)" opacity="0.1" />
        </g>
    )
}

export function ToggleSwitch({ on = false, x = 0, y = 0 }: { on?: boolean; x?: number; y?: number }): JSX.Element {
    return (
        <g transform={`translate(${x}, ${y})`}>
            <rect
                x="0"
                y="0"
                width="36"
                height="20"
                rx="10"
                fill={on ? 'var(--hog-body)' : 'var(--hog-outline)'}
                opacity={on ? 1 : 0.3}
            />
            <circle cx={on ? 26 : 10} cy="10" r="7" fill="var(--hog-belly)" />
        </g>
    )
}

export function FlagPole({ x = 0, y = 0 }: { x?: number; y?: number }): JSX.Element {
    return (
        <g transform={`translate(${x}, ${y})`}>
            <line x1="0" y1="0" x2="0" y2="50" stroke="var(--hog-outline)" strokeWidth="2" strokeLinecap="round" />
            <path d="M2,-2 L28,8 L2,18 Z" fill="var(--hog-body)" stroke="var(--hog-outline)" strokeWidth="1" />
        </g>
    )
}

export function ABLabel({ variant, x = 0, y = 0 }: { variant: 'A' | 'B'; x?: number; y?: number }): JSX.Element {
    return (
        <g transform={`translate(${x}, ${y})`}>
            <rect
                x="0"
                y="0"
                width="24"
                height="24"
                rx="4"
                fill={variant === 'A' ? 'var(--hog-body)' : 'var(--hog-cheek)'}
            />
            <text
                x="12"
                y="17"
                textAnchor="middle"
                fill="var(--hog-belly)"
                fontSize="14"
                fontWeight="bold"
                fontFamily="sans-serif"
            >
                {variant}
            </text>
        </g>
    )
}

export function SurveyForm({ x = 0, y = 0 }: { x?: number; y?: number }): JSX.Element {
    return (
        <g transform={`translate(${x}, ${y})`}>
            <rect
                x="0"
                y="0"
                width="70"
                height="60"
                rx="4"
                fill="var(--hog-belly)"
                stroke="var(--hog-outline)"
                strokeWidth="1.5"
            />
            {/* Question text */}
            <rect x="6" y="6" width="40" height="3" rx="1" fill="var(--hog-outline)" opacity="0.3" />
            {/* Radio options */}
            <circle cx="10" cy="20" r="4" fill="none" stroke="var(--hog-outline)" strokeWidth="1" />
            <rect x="18" y="18" width="30" height="3" rx="1" fill="var(--hog-outline)" opacity="0.2" />
            <circle cx="10" cy="32" r="4" fill="var(--hog-body)" stroke="var(--hog-outline)" strokeWidth="1" />
            <rect x="18" y="30" width="25" height="3" rx="1" fill="var(--hog-outline)" opacity="0.2" />
            {/* Submit button */}
            <rect x="6" y="44" width="30" height="10" rx="3" fill="var(--hog-body)" />
        </g>
    )
}

export function DataBox({ x = 0, y = 0, label = '' }: { x?: number; y?: number; label?: string }): JSX.Element {
    return (
        <g transform={`translate(${x}, ${y})`}>
            <rect
                x="0"
                y="0"
                width="30"
                height="24"
                rx="3"
                fill="var(--hog-belly)"
                stroke="var(--hog-outline)"
                strokeWidth="1"
            />
            <rect x="3" y="3" width="24" height="4" rx="1" fill="var(--hog-body)" opacity="0.5" />
            <rect x="3" y="10" width="18" height="3" rx="1" fill="var(--hog-outline)" opacity="0.15" />
            <rect x="3" y="16" width="12" height="3" rx="1" fill="var(--hog-outline)" opacity="0.1" />
            {label && (
                <text
                    x="15"
                    y="-3"
                    textAnchor="middle"
                    fontSize="7"
                    fill="var(--hog-outline)"
                    opacity="0.5"
                    fontFamily="sans-serif"
                >
                    {label}
                </text>
            )}
        </g>
    )
}

export function PipeSegment({ x1, y1, x2, y2 }: { x1: number; y1: number; x2: number; y2: number }): JSX.Element {
    return (
        <line
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke="var(--hog-body)"
            strokeWidth="6"
            strokeLinecap="round"
            opacity="0.6"
        />
    )
}

export function BugIcon({ x = 0, y = 0 }: { x?: number; y?: number }): JSX.Element {
    return (
        <g transform={`translate(${x}, ${y})`}>
            {/* Bug body */}
            <ellipse cx="0" cy="0" rx="8" ry="10" fill="var(--hog-cheek)" stroke="var(--hog-outline)" strokeWidth="1" />
            {/* Eyes */}
            <circle cx="-3" cy="-4" r="1.5" fill="var(--hog-belly)" />
            <circle cx="3" cy="-4" r="1.5" fill="var(--hog-belly)" />
            {/* Antennae */}
            <line x1="-3" y1="-10" x2="-6" y2="-16" stroke="var(--hog-outline)" strokeWidth="1" strokeLinecap="round" />
            <line x1="3" y1="-10" x2="6" y2="-16" stroke="var(--hog-outline)" strokeWidth="1" strokeLinecap="round" />
            {/* Legs */}
            <line x1="-8" y1="-3" x2="-13" y2="-6" stroke="var(--hog-outline)" strokeWidth="1" strokeLinecap="round" />
            <line x1="-8" y1="3" x2="-13" y2="6" stroke="var(--hog-outline)" strokeWidth="1" strokeLinecap="round" />
            <line x1="8" y1="-3" x2="13" y2="-6" stroke="var(--hog-outline)" strokeWidth="1" strokeLinecap="round" />
            <line x1="8" y1="3" x2="13" y2="6" stroke="var(--hog-outline)" strokeWidth="1" strokeLinecap="round" />
        </g>
    )
}

export function LogLine({ x = 0, y = 0, width = 50 }: { x?: number; y?: number; width?: number }): JSX.Element {
    return (
        <g transform={`translate(${x}, ${y})`}>
            <rect x="0" y="0" width={8} height="4" rx="1" fill="var(--hog-body)" opacity="0.6" />
            <rect x="12" y="0" width={width} height="4" rx="1" fill="var(--hog-outline)" opacity="0.15" />
        </g>
    )
}

export function ChatBubble({
    x = 0,
    y = 0,
    side = 'left',
}: {
    x?: number
    y?: number
    side?: 'left' | 'right'
}): JSX.Element {
    const isLeft = side === 'left'
    return (
        <g transform={`translate(${x}, ${y})`}>
            <rect
                x={isLeft ? 0 : 10}
                y="0"
                width="50"
                height="20"
                rx="8"
                fill={isLeft ? 'var(--hog-belly)' : 'var(--hog-body)'}
                stroke="var(--hog-outline)"
                strokeWidth="1"
                opacity={isLeft ? 1 : 0.8}
            />
            {/* Text lines */}
            <rect x={isLeft ? 6 : 16} y="6" width="30" height="2.5" rx="1" fill="var(--hog-outline)" opacity="0.2" />
            <rect x={isLeft ? 6 : 16} y="11" width="20" height="2.5" rx="1" fill="var(--hog-outline)" opacity="0.15" />
        </g>
    )
}

export function QueryBox({ x = 0, y = 0 }: { x?: number; y?: number }): JSX.Element {
    return (
        <g transform={`translate(${x}, ${y})`}>
            <rect
                x="0"
                y="0"
                width="70"
                height="35"
                rx="3"
                fill="var(--hog-outline)"
                opacity="0.08"
                stroke="var(--hog-outline)"
                strokeWidth="1"
            />
            {/* "SELECT" keyword */}
            <text x="5" y="12" fontSize="7" fill="var(--hog-body)" fontFamily="monospace" fontWeight="bold">
                SELECT
            </text>
            <text x="5" y="22" fontSize="7" fill="var(--hog-outline)" opacity="0.5" fontFamily="monospace">
                FROM events
            </text>
            <text x="5" y="32" fontSize="7" fill="var(--hog-outline)" opacity="0.4" fontFamily="monospace">
                WHERE ...
            </text>
        </g>
    )
}
