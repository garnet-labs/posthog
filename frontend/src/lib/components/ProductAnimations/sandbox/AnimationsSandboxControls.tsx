import { LemonSegmentedButton } from '@posthog/lemon-ui'

import type { AnimationMode, AnimationSize } from '../types'

interface AnimationsSandboxControlsProps {
    size: AnimationSize
    mode: AnimationMode
    onSizeChange: (size: AnimationSize) => void
    onModeChange: (mode: AnimationMode) => void
}

export function AnimationsSandboxControls({
    size,
    mode,
    onSizeChange,
    onModeChange,
}: AnimationsSandboxControlsProps): JSX.Element {
    return (
        <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase text-muted">Size</span>
                <LemonSegmentedButton
                    value={size}
                    onChange={(val) => onSizeChange(val as AnimationSize)}
                    options={[
                        { value: 'small', label: 'Small (48px)' },
                        { value: 'medium', label: 'Medium (200px)' },
                        { value: 'large', label: 'Large (400px)' },
                    ]}
                    size="small"
                />
            </div>
            <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase text-muted">Mode</span>
                <LemonSegmentedButton
                    value={mode}
                    onChange={(val) => onModeChange(val as AnimationMode)}
                    options={[
                        { value: 'loop', label: 'Loop' },
                        { value: 'once', label: 'Play once' },
                    ]}
                    size="small"
                />
            </div>
            <p className="text-xs text-muted">
                To test reduced motion, enable it in Chrome DevTools → Rendering → Emulate CSS prefers-reduced-motion.
            </p>
        </div>
    )
}
