import type { ReactNode } from 'react'

import { SIZE_MAP } from '../types'
import type { AnimationSize } from '../types'
import { SvgIdContext, useSvgIdPrefix } from './useSvgIds'

interface AnimationCanvasProps {
    size: AnimationSize
    children: ReactNode
    className?: string
}

export function AnimationCanvas({ size, children, className }: AnimationCanvasProps): JSX.Element {
    const px = SIZE_MAP[size]
    const idPrefix = useSvgIdPrefix()

    return (
        <SvgIdContext.Provider value={idPrefix}>
            <svg
                viewBox="0 0 200 200"
                width={px}
                height={px}
                xmlns="http://www.w3.org/2000/svg"
                className={className}
                role="img"
                aria-hidden="true"
                style={
                    {
                        '--hog-body': 'var(--color-warning-light, #F7A501)',
                        '--hog-spines': 'var(--color-text-primary, #2D2D2D)',
                        '--hog-belly': 'var(--color-bg-surface-primary, #FFFFFF)',
                        '--hog-outline': 'var(--color-text-primary, #2D2D2D)',
                        '--hog-cheek': 'var(--color-danger-light, #FF8A80)',
                        '--hog-eye': 'var(--color-text-primary, #2D2D2D)',
                    } as React.CSSProperties
                }
            >
                {children}
            </svg>
        </SvgIdContext.Provider>
    )
}
