/**
 * Error tracking: Hedgehog spots a bug, catches it with a net.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { BugIcon } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function ErrorTrackingAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    <BugIcon x={140} y={50} />
                    {/* Net */}
                    <ellipse
                        cx="145"
                        cy="55"
                        rx="18"
                        ry="14"
                        fill="none"
                        stroke="var(--hog-outline)"
                        strokeWidth="1.5"
                        strokeDasharray="3 2"
                    />
                    <g transform="translate(-25, 35) scale(0.45)">
                        <HedgehogCharacter pose="standing" expression="surprised" />
                    </g>
                </>
            ) : (
                <>
                    {/* Bug bouncing around */}
                    <m.g
                        animate={{
                            x: [0, 20, -10, 30, 0],
                            y: [0, -15, 10, -5, 0],
                        }}
                        transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                    >
                        <BugIcon x={130} y={50} />
                    </m.g>
                    {/* Net swoops in */}
                    <m.ellipse
                        cx="145"
                        cy="55"
                        rx="18"
                        ry="14"
                        fill="none"
                        stroke="var(--hog-outline)"
                        strokeWidth="1.5"
                        strokeDasharray="3 2"
                        initial={{ scale: 0, opacity: 0 }}
                        animate={{ scale: [0, 1.2, 1], opacity: [0, 1, 1] }}
                        transition={{ delay: 1.5, duration: 0.5 }}
                    />
                    {/* Hedgehog alert then catching */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-25, 35) scale(0.45)">
                            <m.g
                                animate={{ x: [0, 5, 0] }}
                                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                            >
                                <HedgehogCharacter pose="standing" expression="surprised" />
                            </m.g>
                        </g>
                    </m.g>
                </>
            )}
        </AnimationCanvas>
    )
}

export default ErrorTrackingAnimation
