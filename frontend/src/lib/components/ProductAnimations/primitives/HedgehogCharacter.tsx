import { HedgehogArm, HedgehogBelly, HedgehogBody, HedgehogFace, HedgehogLegs, HedgehogSpines } from './HedgehogParts'
import type { HedgehogExpression } from './HedgehogParts'

export type HedgehogPose = 'standing' | 'sitting' | 'walking' | 'leaning' | 'typing'

interface HedgehogCharacterProps {
    pose?: HedgehogPose
    expression?: HedgehogExpression
    className?: string
}

function getTransformForPose(pose: HedgehogPose): string {
    switch (pose) {
        case 'sitting':
            return 'translate(0, 10)'
        case 'walking':
            // Slight forward lean
            return 'rotate(-5, 100, 120)'
        case 'leaning':
            return 'rotate(8, 100, 140)'
        case 'typing':
            // Slight forward lean with lower center
            return 'rotate(-8, 100, 130)'
        case 'standing':
        default:
            return ''
    }
}

export function HedgehogCharacter({ pose = 'standing', expression = 'neutral' }: HedgehogCharacterProps): JSX.Element {
    const transform = getTransformForPose(pose)

    return (
        <g transform={transform}>
            {/* Render back to front for correct layering */}
            {/* 1. Spines (behind everything) */}
            <HedgehogSpines />
            {/* 2. Body */}
            <HedgehogBody />
            {/* 3. Belly (on top of body) */}
            <HedgehogBelly />
            {/* 4. Arms (behind face but in front of body) */}
            <HedgehogArm side="left" />
            <HedgehogArm side="right" />
            {/* 5. Legs */}
            <HedgehogLegs />
            {/* 6. Face (on top of everything) */}
            <HedgehogFace expression={expression} />
        </g>
    )
}
