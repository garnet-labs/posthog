/**
 * SQL/HogQL: Hedgehog types a query, table of results appears.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { QueryBox } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function SqlAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    <QueryBox x={65} y={15} />
                    {/* Results table */}
                    <rect
                        x="65"
                        y="60"
                        width="70"
                        height="40"
                        rx="2"
                        fill="var(--hog-belly)"
                        stroke="var(--hog-outline)"
                        strokeWidth="1"
                    />
                    <line
                        x1="65"
                        y1="72"
                        x2="135"
                        y2="72"
                        stroke="var(--hog-outline)"
                        strokeWidth="0.5"
                        opacity="0.3"
                    />
                    <line
                        x1="65"
                        y1="82"
                        x2="135"
                        y2="82"
                        stroke="var(--hog-outline)"
                        strokeWidth="0.5"
                        opacity="0.2"
                    />
                    <line
                        x1="65"
                        y1="92"
                        x2="135"
                        y2="92"
                        stroke="var(--hog-outline)"
                        strokeWidth="0.5"
                        opacity="0.15"
                    />
                    <g transform="translate(-25, 30) scale(0.45)">
                        <HedgehogCharacter pose="standing" expression="focused" />
                    </g>
                </>
            ) : (
                <>
                    {/* Query box appears */}
                    <m.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5 }}>
                        <QueryBox x={65} y={15} />
                    </m.g>
                    {/* Typing cursor blinks */}
                    <m.rect
                        x="60"
                        y="37"
                        width="2"
                        height="8"
                        fill="var(--hog-body)"
                        animate={{ opacity: [1, 0, 1] }}
                        transition={{ duration: 1, repeat: Infinity }}
                    />
                    {/* Results appear */}
                    <m.g
                        initial={{ y: 10, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        transition={{ delay: 1.5, duration: 0.5, ease: 'easeOut' }}
                    >
                        <rect
                            x="65"
                            y="60"
                            width="70"
                            height="40"
                            rx="2"
                            fill="var(--hog-belly)"
                            stroke="var(--hog-outline)"
                            strokeWidth="1"
                        />
                        <line
                            x1="65"
                            y1="72"
                            x2="135"
                            y2="72"
                            stroke="var(--hog-outline)"
                            strokeWidth="0.5"
                            opacity="0.3"
                        />
                        <line
                            x1="65"
                            y1="82"
                            x2="135"
                            y2="82"
                            stroke="var(--hog-outline)"
                            strokeWidth="0.5"
                            opacity="0.2"
                        />
                        <line
                            x1="65"
                            y1="92"
                            x2="135"
                            y2="92"
                            stroke="var(--hog-outline)"
                            strokeWidth="0.5"
                            opacity="0.15"
                        />
                    </m.g>
                    {/* Hedgehog typing */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-25, 30) scale(0.45)">
                            <HedgehogCharacter pose="standing" expression="focused" />
                        </g>
                    </m.g>
                </>
            )}
        </AnimationCanvas>
    )
}

export default SqlAnimation
