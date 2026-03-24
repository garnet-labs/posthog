/**
 * Session replay: Hedgehog watches a screen recording playback, reacts to user actions.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { MiniScreen } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function SessionReplayAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    <MiniScreen x={55} y={20} />
                    {/* Play button overlay */}
                    <polygon points="85,42 100,50 85,58" fill="var(--hog-body)" opacity="0.8" />
                    <g transform="translate(-15, 40) scale(0.45)">
                        <HedgehogCharacter pose="sitting" expression="focused" />
                    </g>
                </>
            ) : (
                <>
                    {/* Screen slides in */}
                    <m.g
                        initial={{ y: -20, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        transition={{ duration: 0.6, ease: 'easeOut' }}
                    >
                        <MiniScreen x={55} y={20} />
                        {/* Animated cursor moving on screen */}
                        <m.circle
                            cx={80}
                            cy={45}
                            r={3}
                            fill="var(--hog-cheek)"
                            animate={{
                                cx: [80, 100, 115, 95, 80],
                                cy: [45, 38, 50, 55, 45],
                            }}
                            transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
                        />
                    </m.g>
                    {/* Hedgehog watching */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-15, 40) scale(0.45)">
                            <m.g
                                animate={{ rotate: [0, -2, 0, 2, 0] }}
                                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                            >
                                <HedgehogCharacter pose="sitting" expression="focused" />
                            </m.g>
                        </g>
                    </m.g>
                </>
            )}
        </AnimationCanvas>
    )
}

export default SessionReplayAnimation
