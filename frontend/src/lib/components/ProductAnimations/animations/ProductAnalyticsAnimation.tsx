/**
 * Product analytics: Hedgehog watches a trend line draw itself, points at the peak, celebrates.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { ChartGrid, DataPoints, TrendLine } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function ProductAnalyticsAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    <ChartGrid />
                    <TrendLine />
                    <DataPoints />
                    <g transform="translate(-30, 30) scale(0.5)">
                        <HedgehogCharacter pose="standing" expression="happy" />
                    </g>
                </>
            ) : (
                <>
                    <ChartGrid />
                    {/* Trend line draws in */}
                    <m.path
                        d="M20,160 Q50,150 70,130 T110,90 T150,50 T180,30"
                        fill="none"
                        stroke="var(--hog-body)"
                        strokeWidth="3"
                        strokeLinecap="round"
                        initial={{ pathLength: 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ duration: 2, ease: 'easeOut' }}
                    />
                    {/* Data points pop in */}
                    <m.g
                        initial={{ opacity: 0, scale: 0 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 1.5, duration: 0.5, staggerChildren: 0.15 }}
                    >
                        <DataPoints />
                    </m.g>
                    {/* Hedgehog watches then celebrates */}
                    <m.g variants={breathe} animate="idle" style={{ transformOrigin: 'center' }}>
                        <g transform="translate(-30, 30) scale(0.5)">
                            <m.g
                                initial={{ y: 0 }}
                                animate={{ y: [0, -5, 0] }}
                                transition={{ delay: 2.2, duration: 0.4, ease: 'easeOut' }}
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

export default ProductAnalyticsAnimation
