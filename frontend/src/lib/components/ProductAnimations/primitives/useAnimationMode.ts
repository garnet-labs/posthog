import { useReducedMotion } from 'motion/react'

import type { AnimationMode } from '../types'

interface AnimationModeResult {
    shouldAnimate: boolean
    resolvedMode: AnimationMode | 'static'
}

export function useAnimationMode(requestedMode: AnimationMode): AnimationModeResult {
    const prefersReduced = useReducedMotion()
    return {
        shouldAnimate: !prefersReduced,
        resolvedMode: prefersReduced ? 'static' : requestedMode,
    }
}
