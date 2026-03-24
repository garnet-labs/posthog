/**
 * Data pipelines: Hedgehog directs data flow through connected pipes.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { PipeSegment } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function DataPipelinesAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    {/* Pipeline structure */}
                    <PipeSegment x1={20} y1={60} x2={80} y2={60} />
                    <PipeSegment x1={80} y1={60} x2={80} y2={100} />
                    <PipeSegment x1={80} y1={100} x2={160} y2={100} />
                    <PipeSegment x1={160} y1={100} x2={160} y2={140} />
                    <PipeSegment x1={160} y1={140} x2={190} y2={140} />
                    {/* Data dots along pipe */}
                    <circle cx="50" cy="60" r="4" fill="var(--hog-belly)" stroke="var(--hog-body)" strokeWidth="1.5" />
                    <circle
                        cx="120"
                        cy="100"
                        r="4"
                        fill="var(--hog-belly)"
                        stroke="var(--hog-body)"
                        strokeWidth="1.5"
                    />
                    <circle
                        cx="175"
                        cy="140"
                        r="4"
                        fill="var(--hog-belly)"
                        stroke="var(--hog-body)"
                        strokeWidth="1.5"
                    />
                    <g transform="translate(-15, 45) scale(0.42)">
                        <HedgehogCharacter pose="standing" expression="happy" />
                    </g>
                </>
            ) : (
                <>
                    {/* Pipes draw in */}
                    <m.line
                        x1={20}
                        y1={60}
                        x2={80}
                        y2={60}
                        stroke="var(--hog-body)"
                        strokeWidth="6"
                        strokeLinecap="round"
                        opacity="0.6"
                        initial={{ pathLength: 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ duration: 0.5 }}
                    />
                    <m.line
                        x1={80}
                        y1={60}
                        x2={80}
                        y2={100}
                        stroke="var(--hog-body)"
                        strokeWidth="6"
                        strokeLinecap="round"
                        opacity="0.6"
                        initial={{ pathLength: 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ delay: 0.4, duration: 0.4 }}
                    />
                    <m.line
                        x1={80}
                        y1={100}
                        x2={160}
                        y2={100}
                        stroke="var(--hog-body)"
                        strokeWidth="6"
                        strokeLinecap="round"
                        opacity="0.6"
                        initial={{ pathLength: 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ delay: 0.7, duration: 0.5 }}
                    />
                    <m.line
                        x1={160}
                        y1={100}
                        x2={160}
                        y2={140}
                        stroke="var(--hog-body)"
                        strokeWidth="6"
                        strokeLinecap="round"
                        opacity="0.6"
                        initial={{ pathLength: 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ delay: 1.1, duration: 0.3 }}
                    />
                    <m.line
                        x1={160}
                        y1={140}
                        x2={190}
                        y2={140}
                        stroke="var(--hog-body)"
                        strokeWidth="6"
                        strokeLinecap="round"
                        opacity="0.6"
                        initial={{ pathLength: 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ delay: 1.3, duration: 0.3 }}
                    />
                    {/* Data dots flow through */}
                    <m.circle
                        r="4"
                        fill="var(--hog-belly)"
                        stroke="var(--hog-body)"
                        strokeWidth="1.5"
                        animate={{ cx: [20, 80, 80, 160, 160, 190], cy: [60, 60, 100, 100, 140, 140] }}
                        transition={{ duration: 3, repeat: Infinity, ease: 'linear', delay: 1.5 }}
                    />
                    {/* Hedgehog directing */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-15, 45) scale(0.42)">
                            <HedgehogCharacter pose="standing" expression="happy" />
                        </g>
                    </m.g>
                </>
            )}
        </AnimationCanvas>
    )
}

export default DataPipelinesAnimation
