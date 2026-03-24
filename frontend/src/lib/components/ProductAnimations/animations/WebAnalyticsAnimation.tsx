/**
 * Web analytics: Hedgehog browses pages, sees traffic data flowing in.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { BarChart, ChartGrid } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function WebAnalyticsAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    <ChartGrid />
                    <BarChart />
                    <g transform="translate(-20, 35) scale(0.45)">
                        <HedgehogCharacter pose="standing" expression="curious" />
                    </g>
                </>
            ) : (
                <>
                    <ChartGrid />
                    {/* Bars grow up */}
                    <m.g
                        initial={{ scaleY: 0 }}
                        animate={{ scaleY: 1 }}
                        transition={{ duration: 1.2, ease: 'easeOut' }}
                        style={{ transformOrigin: 'bottom' }}
                    >
                        <BarChart />
                    </m.g>
                    {/* Hedgehog watches data */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-20, 35) scale(0.45)">
                            <m.g
                                animate={{ x: [0, 3, 0, -3, 0] }}
                                transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
                            >
                                <HedgehogCharacter pose="standing" expression="curious" />
                            </m.g>
                        </g>
                    </m.g>
                </>
            )}
        </AnimationCanvas>
    )
}

export default WebAnalyticsAnimation
