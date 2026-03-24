import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import type { AnimationComponentProps } from '../types'

function FallbackAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <HedgehogCharacter pose="standing" expression="happy" />
            ) : (
                <m.g variants={breathe} animate="idle">
                    <HedgehogCharacter pose="standing" expression="happy" />
                </m.g>
            )}
        </AnimationCanvas>
    )
}

export default FallbackAnimation
