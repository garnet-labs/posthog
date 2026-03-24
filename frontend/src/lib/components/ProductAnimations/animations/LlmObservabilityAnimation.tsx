/**
 * LLM observability: Hedgehog monitors AI conversation bubbles, checks metrics.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { ChatBubble } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function LlmObservabilityAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    <ChatBubble x={60} y={15} side="left" />
                    <ChatBubble x={80} y={45} side="right" />
                    <ChatBubble x={60} y={75} side="left" />
                    {/* Metrics badge */}
                    <rect x="145" y="20" width="40" height="18" rx="3" fill="var(--hog-body)" opacity="0.8" />
                    <text
                        x="165"
                        y="33"
                        textAnchor="middle"
                        fontSize="8"
                        fill="var(--hog-belly)"
                        fontFamily="monospace"
                    >
                        0.8s
                    </text>
                    <g transform="translate(-25, 40) scale(0.4)">
                        <HedgehogCharacter pose="standing" expression="curious" />
                    </g>
                </>
            ) : (
                <>
                    {/* Chat bubbles appear in sequence */}
                    <m.g initial={{ x: -20, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.4 }}>
                        <ChatBubble x={60} y={15} side="left" />
                    </m.g>
                    <m.g
                        initial={{ x: 20, opacity: 0 }}
                        animate={{ x: 0, opacity: 1 }}
                        transition={{ delay: 0.6, duration: 0.4 }}
                    >
                        <ChatBubble x={80} y={45} side="right" />
                    </m.g>
                    <m.g
                        initial={{ x: -20, opacity: 0 }}
                        animate={{ x: 0, opacity: 1 }}
                        transition={{ delay: 1.2, duration: 0.4 }}
                    >
                        <ChatBubble x={60} y={75} side="left" />
                    </m.g>
                    {/* Metrics badge pops in */}
                    <m.g
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ delay: 1.8, duration: 0.3, type: 'spring', stiffness: 300 }}
                    >
                        <rect x="145" y="20" width="40" height="18" rx="3" fill="var(--hog-body)" opacity="0.8" />
                        <text
                            x="165"
                            y="33"
                            textAnchor="middle"
                            fontSize="8"
                            fill="var(--hog-belly)"
                            fontFamily="monospace"
                        >
                            0.8s
                        </text>
                    </m.g>
                    {/* Hedgehog monitoring */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-25, 40) scale(0.4)">
                            <m.g animate={{ y: [0, -2, 0] }} transition={{ delay: 2, duration: 0.4, ease: 'easeOut' }}>
                                <HedgehogCharacter pose="standing" expression="curious" />
                            </m.g>
                        </g>
                    </m.g>
                </>
            )}
        </AnimationCanvas>
    )
}

export default LlmObservabilityAnimation
