/**
 * Logs: Hedgehog scrolls through log entries, highlights one.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { LogLine } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function LogsAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    {/* Log panel */}
                    <rect
                        x="55"
                        y="10"
                        width="135"
                        height="110"
                        rx="4"
                        fill="var(--hog-outline)"
                        opacity="0.05"
                        stroke="var(--hog-outline)"
                        strokeWidth="1"
                    />
                    <LogLine x={62} y={20} width={55} />
                    <LogLine x={62} y={30} width={45} />
                    <LogLine x={62} y={40} width={60} />
                    {/* Highlighted line */}
                    <rect x="58" y="48" width="126" height="10" rx="2" fill="var(--hog-body)" opacity="0.15" />
                    <LogLine x={62} y={50} width={50} />
                    <LogLine x={62} y={62} width={40} />
                    <LogLine x={62} y={72} width={55} />
                    <LogLine x={62} y={82} width={35} />
                    <LogLine x={62} y={92} width={48} />
                    <LogLine x={62} y={102} width={42} />
                    <g transform="translate(-30, 30) scale(0.42)">
                        <HedgehogCharacter pose="standing" expression="focused" />
                    </g>
                </>
            ) : (
                <>
                    {/* Log panel */}
                    <m.rect
                        x="55"
                        y="10"
                        width="135"
                        height="110"
                        rx="4"
                        fill="var(--hog-outline)"
                        opacity="0.05"
                        stroke="var(--hog-outline)"
                        strokeWidth="1"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ duration: 0.3 }}
                    />
                    {/* Log lines stream in */}
                    {[20, 30, 40, 50, 62, 72, 82, 92, 102].map((y, i) => (
                        <m.g
                            key={y}
                            initial={{ x: 10, opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            transition={{ delay: 0.2 + i * 0.15, duration: 0.3 }}
                        >
                            <LogLine x={62} y={y} width={35 + ((i * 17) % 25)} />
                        </m.g>
                    ))}
                    {/* Highlight slides over one entry */}
                    <m.rect
                        x="58"
                        y="48"
                        width="126"
                        height="10"
                        rx="2"
                        fill="var(--hog-body)"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: [0, 0, 0.15, 0.15] }}
                        transition={{ delay: 1.5, duration: 1 }}
                    />
                    {/* Hedgehog reading */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-30, 30) scale(0.42)">
                            <HedgehogCharacter pose="standing" expression="focused" />
                        </g>
                    </m.g>
                </>
            )}
        </AnimationCanvas>
    )
}

export default LogsAnimation
