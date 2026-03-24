// Primary public API
export { ProductAnimation } from './ProductAnimation'

// Primitives for animation authors (used by product-specific animations)
export { AnimationCanvas } from './primitives/AnimationCanvas'
export { HedgehogCharacter } from './primitives/HedgehogCharacter'
export { useAnimationMode } from './primitives/useAnimationMode'
export { useSvgIds, SvgIdContext } from './primitives/useSvgIds'
export * from './primitives/AnimationPresets'

// Types
export type { AnimationSize, AnimationMode, AnimationComponentProps, ProductAnimationProps } from './types'
export type { HedgehogPose } from './primitives/HedgehogCharacter'
export type { HedgehogExpression } from './primitives/HedgehogParts'
