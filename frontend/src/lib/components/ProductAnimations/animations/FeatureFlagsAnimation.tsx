/**
 * Feature flags: Hedgehog toggles a flag switch on/off, sees UI change.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { FlagPole, ToggleSwitch } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function FeatureFlagsAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    <FlagPole x={140} y={30} />
                    <ToggleSwitch on={true} x={100} y={100} />
                    <g transform="translate(-25, 30) scale(0.5)">
                        <HedgehogCharacter pose="standing" expression="happy" />
                    </g>
                </>
            ) : (
                <>
                    {/* Flag pole */}
                    <m.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
                        <FlagPole x={140} y={30} />
                    </m.g>
                    {/* Toggle switch animating on/off */}
                    <m.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3, duration: 0.4 }}>
                        {/* Track */}
                        <rect x="100" y="100" width="36" height="20" rx="10" fill="var(--hog-body)" />
                        {/* Knob slides back and forth */}
                        <m.circle
                            cy={110}
                            r={7}
                            fill="var(--hog-belly)"
                            animate={{ cx: [110, 126, 110, 126] }}
                            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut', times: [0, 0.3, 0.6, 1] }}
                        />
                    </m.g>
                    {/* Hedgehog reaching for toggle */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-25, 30) scale(0.5)">
                            <m.g
                                animate={{ x: [0, 3, 0] }}
                                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
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

export default FeatureFlagsAnimation
