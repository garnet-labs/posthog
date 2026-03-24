import type { ComponentType } from 'react'

export type AnimationSize = 'small' | 'medium' | 'large'
export type AnimationMode = 'loop' | 'once'

export const SIZE_MAP: Record<AnimationSize, number> = {
    small: 48,
    medium: 200,
    large: 400,
} as const

export interface AnimationComponentProps {
    size: AnimationSize
    mode: AnimationMode | 'static'
}

export interface ProductAnimationProps {
    product: string
    size?: AnimationSize
    mode?: AnimationMode
    className?: string
    onComplete?: () => void
    /** When true, animation plays on hover and shows static state otherwise (INFR-03) */
    hover?: boolean
}

export type LazyAnimationFactory = () => Promise<{ default: ComponentType<AnimationComponentProps> }>
