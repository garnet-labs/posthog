/**
 * Experiments: Hedgehog compares A/B variants side by side, picks winner.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { ABLabel } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function ExperimentsAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    <ABLabel variant="A" x={30} y={25} />
                    <ABLabel variant="B" x={146} y={25} />
                    {/* Result bars */}
                    <rect x="30" y="55" width="24" height="60" rx="3" fill="var(--hog-body)" opacity="0.5" />
                    <rect x="146" y="35" width="24" height="80" rx="3" fill="var(--hog-cheek)" opacity="0.6" />
                    {/* Crown on B */}
                    <text x="158" y="28" textAnchor="middle" fontSize="16">
                        👑
                    </text>
                    <g transform="translate(-10, 45) scale(0.4)">
                        <HedgehogCharacter pose="standing" expression="happy" />
                    </g>
                </>
            ) : (
                <>
                    {/* Labels slide in */}
                    <m.g initial={{ x: -30, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.5 }}>
                        <ABLabel variant="A" x={30} y={25} />
                    </m.g>
                    <m.g initial={{ x: 30, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.5 }}>
                        <ABLabel variant="B" x={146} y={25} />
                    </m.g>
                    {/* Bars grow */}
                    <m.rect
                        x="30"
                        y="55"
                        width="24"
                        rx="3"
                        fill="var(--hog-body)"
                        opacity="0.5"
                        initial={{ height: 0 }}
                        animate={{ height: 60 }}
                        transition={{ delay: 0.6, duration: 1, ease: 'easeOut' }}
                    />
                    <m.rect
                        x="146"
                        y="35"
                        width="24"
                        rx="3"
                        fill="var(--hog-cheek)"
                        opacity="0.6"
                        initial={{ height: 0 }}
                        animate={{ height: 80 }}
                        transition={{ delay: 0.6, duration: 1.2, ease: 'easeOut' }}
                    />
                    {/* Crown appears on winner */}
                    <m.text
                        x="158"
                        y="28"
                        textAnchor="middle"
                        fontSize="16"
                        initial={{ opacity: 0, scale: 0 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 2, duration: 0.4, type: 'spring', stiffness: 300, damping: 15 }}
                    >
                        👑
                    </m.text>
                    {/* Hedgehog celebrates */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-10, 45) scale(0.4)">
                            <m.g
                                initial={{ y: 0 }}
                                animate={{ y: [0, -6, 0] }}
                                transition={{ delay: 2.2, duration: 0.5 }}
                            >
                                <HedgehogCharacter pose="standing" expression="happy" />
                            </m.g>
                        </g>
                    </m.g>
                </>
            )}
        </AnimationCanvas>
    )
}

export default ExperimentsAnimation
