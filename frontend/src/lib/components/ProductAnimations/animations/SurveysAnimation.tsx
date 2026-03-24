/**
 * Surveys: Hedgehog fills out a survey form, submits with satisfaction.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { SurveyForm } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function SurveysAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    <SurveyForm x={65} y={15} />
                    <g transform="translate(-20, 35) scale(0.45)">
                        <HedgehogCharacter pose="standing" expression="focused" />
                    </g>
                </>
            ) : (
                <>
                    {/* Survey form slides in */}
                    <m.g initial={{ y: -15, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.5 }}>
                        <SurveyForm x={65} y={15} />
                        {/* Animated checkmark on selected option */}
                        <m.circle
                            cx={75}
                            cy={47}
                            r={3}
                            fill="var(--hog-body)"
                            initial={{ scale: 0 }}
                            animate={{ scale: 1 }}
                            transition={{ delay: 1.2, duration: 0.3, type: 'spring', stiffness: 400 }}
                        />
                    </m.g>
                    {/* Hedgehog typing/filling */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-20, 35) scale(0.45)">
                            <m.g
                                animate={{ x: [0, 2, 0, -1, 0] }}
                                transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
                            >
                                <HedgehogCharacter pose="standing" expression="focused" />
                            </m.g>
                        </g>
                    </m.g>
                </>
            )}
        </AnimationCanvas>
    )
}

export default SurveysAnimation
