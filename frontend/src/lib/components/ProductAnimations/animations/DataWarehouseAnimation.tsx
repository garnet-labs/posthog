/**
 * Data warehouse: Hedgehog organizes data into shelves/boxes.
 */
import * as m from 'motion/react-m'

import { AnimationCanvas } from '../primitives/AnimationCanvas'
import { breathe } from '../primitives/AnimationPresets'
import { HedgehogCharacter } from '../primitives/HedgehogCharacter'
import { DataBox } from '../primitives/ScenePrimitives'
import type { AnimationComponentProps } from '../types'

function DataWarehouseAnimation({ size, mode }: AnimationComponentProps): JSX.Element {
    const isStatic = mode === 'static'

    return (
        <AnimationCanvas size={size}>
            {isStatic ? (
                <>
                    {/* Shelves */}
                    <line
                        x1="60"
                        y1="60"
                        x2="180"
                        y2="60"
                        stroke="var(--hog-outline)"
                        strokeWidth="1.5"
                        opacity="0.3"
                    />
                    <line
                        x1="60"
                        y1="100"
                        x2="180"
                        y2="100"
                        stroke="var(--hog-outline)"
                        strokeWidth="1.5"
                        opacity="0.3"
                    />
                    <line
                        x1="60"
                        y1="140"
                        x2="180"
                        y2="140"
                        stroke="var(--hog-outline)"
                        strokeWidth="1.5"
                        opacity="0.3"
                    />
                    {/* Data boxes on shelves */}
                    <DataBox x={70} y={35} />
                    <DataBox x={110} y={35} />
                    <DataBox x={150} y={35} />
                    <DataBox x={80} y={75} />
                    <DataBox x={130} y={75} />
                    <DataBox x={90} y={115} />
                    <g transform="translate(-30, 40) scale(0.42)">
                        <HedgehogCharacter pose="standing" expression="focused" />
                    </g>
                </>
            ) : (
                <>
                    {/* Shelves fade in */}
                    <m.g initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} transition={{ duration: 0.5 }}>
                        <line x1="60" y1="60" x2="180" y2="60" stroke="var(--hog-outline)" strokeWidth="1.5" />
                        <line x1="60" y1="100" x2="180" y2="100" stroke="var(--hog-outline)" strokeWidth="1.5" />
                        <line x1="60" y1="140" x2="180" y2="140" stroke="var(--hog-outline)" strokeWidth="1.5" />
                    </m.g>
                    {/* Boxes slide in staggered */}
                    {[
                        { x: 70, y: 35, delay: 0.3 },
                        { x: 110, y: 35, delay: 0.5 },
                        { x: 150, y: 35, delay: 0.7 },
                        { x: 80, y: 75, delay: 0.9 },
                        { x: 130, y: 75, delay: 1.1 },
                        { x: 90, y: 115, delay: 1.3 },
                    ].map((box, i) => (
                        <m.g
                            key={i}
                            initial={{ y: -20, opacity: 0 }}
                            animate={{ y: 0, opacity: 1 }}
                            transition={{ delay: box.delay, duration: 0.4, type: 'spring', damping: 15 }}
                        >
                            <DataBox x={box.x} y={box.y} />
                        </m.g>
                    ))}
                    {/* Hedgehog organizing */}
                    <m.g variants={breathe} animate="idle">
                        <g transform="translate(-30, 40) scale(0.42)">
                            <HedgehogCharacter pose="standing" expression="focused" />
                        </g>
                    </m.g>
                </>
            )}
        </AnimationCanvas>
    )
}

export default DataWarehouseAnimation
