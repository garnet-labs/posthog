import { LazyMotion, domAnimation } from 'motion/react'
import { Suspense, lazy, memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { AnimationCanvas } from './primitives/AnimationCanvas'
import { HedgehogCharacter } from './primitives/HedgehogCharacter'
import { useAnimationMode } from './primitives/useAnimationMode'
import { animationRegistry } from './registry'
import type { AnimationMode, ProductAnimationProps } from './types'

function StaticFallback({ size }: { size: 'small' | 'medium' | 'large' }): JSX.Element {
    return (
        <AnimationCanvas size={size}>
            <HedgehogCharacter pose="standing" expression="happy" />
        </AnimationCanvas>
    )
}

/** Hook: pause looping animations when off-screen (INFR-05) */
function useVisibilityPause(ref: React.RefObject<HTMLDivElement | null>): boolean {
    const [isVisible, setIsVisible] = useState(true)

    useEffect(() => {
        const el = ref.current
        if (!el) {
            return
        }
        const observer = new IntersectionObserver(([entry]) => setIsVisible(entry.isIntersecting), { threshold: 0.1 })
        observer.observe(el)
        return () => observer.disconnect()
    }, [ref])

    return isVisible
}

function ProductAnimationInner({
    product,
    size = 'medium',
    mode = 'loop',
    className,
    hover,
}: ProductAnimationProps & { hover?: boolean }): JSX.Element {
    const { shouldAnimate, resolvedMode } = useAnimationMode(mode)
    const containerRef = useRef<HTMLDivElement>(null)
    const isVisible = useVisibilityPause(containerRef)
    const [isHovered, setIsHovered] = useState(false)

    const AnimationComponent = useMemo(() => {
        const loader = animationRegistry[product] ?? animationRegistry._fallback
        return lazy(loader)
    }, [product])

    // Determine effective mode considering hover, visibility, and reduced motion
    const effectiveMode = useMemo((): AnimationMode | 'static' => {
        if (!shouldAnimate) {
            return 'static'
        }
        if (hover && !isHovered) {
            return 'static'
        }
        if (!isVisible && resolvedMode === 'loop') {
            return 'static'
        }
        return resolvedMode
    }, [shouldAnimate, hover, isHovered, isVisible, resolvedMode])

    const handleMouseEnter = useCallback((): void => setIsHovered(true), [])
    const handleMouseLeave = useCallback((): void => setIsHovered(false), [])

    return (
        <div
            ref={containerRef}
            className={className}
            onMouseEnter={hover ? handleMouseEnter : undefined}
            onMouseLeave={hover ? handleMouseLeave : undefined}
        >
            <LazyMotion features={domAnimation} strict>
                <Suspense fallback={<StaticFallback size={size} />}>
                    <AnimationComponent size={size} mode={effectiveMode} />
                </Suspense>
            </LazyMotion>
        </div>
    )
}

export const ProductAnimation = memo(ProductAnimationInner)
