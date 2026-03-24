import { useState } from 'react'

import { ProductAnimation } from '../ProductAnimation'
import { animationRegistry } from '../registry'
import type { AnimationMode, AnimationSize } from '../types'
import { AnimationsSandboxControls } from './AnimationsSandboxControls'

const PRODUCT_LABELS: Record<string, string> = {
    product_analytics: 'Product analytics',
    web_analytics: 'Web analytics',
    session_replay: 'Session replay',
    feature_flags: 'Feature flags',
    experiments: 'Experiments',
    surveys: 'Surveys',
    data_warehouse: 'Data warehouse',
    pipeline: 'Data pipelines',
    hog_ql: 'SQL / HogQL',
    error_tracking: 'Error tracking',
    logs: 'Logs',
    llm_observability: 'LLM observability',
}

function AnimationsSandbox(): JSX.Element {
    const [size, setSize] = useState<AnimationSize>('medium')
    const [mode, setMode] = useState<AnimationMode>('loop')

    const productKeys = Object.keys(animationRegistry).filter((k) => k !== '_fallback')

    return (
        <div className="space-y-6 p-4">
            <div>
                <h1 className="text-2xl font-bold">Animations sandbox</h1>
                <p className="mt-1 text-muted">
                    Preview all product animations at different sizes and modes. Hover over a card to see it animate.
                </p>
            </div>

            <AnimationsSandboxControls size={size} mode={mode} onSizeChange={setSize} onModeChange={setMode} />

            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {productKeys.map((key) => (
                    <div key={key} className="flex flex-col items-center gap-3 rounded-lg border p-4">
                        <ProductAnimation product={key} size={size} mode={mode} />
                        <div className="text-center">
                            <span className="block text-sm font-medium">{PRODUCT_LABELS[key] ?? key}</span>
                            <span className="font-mono text-xs text-muted">{key}</span>
                        </div>
                    </div>
                ))}
            </div>

            <div className="border-t pt-4">
                <h2 className="mb-3 text-lg font-semibold">Hover mode demo</h2>
                <p className="mb-3 text-sm text-muted">
                    These use <code>hover=true</code> — static until you hover, then they animate.
                </p>
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {productKeys.slice(0, 6).map((key) => (
                        <div key={`hover-${key}`} className="flex flex-col items-center gap-3 rounded-lg border p-4">
                            <ProductAnimation product={key} size="medium" mode="loop" hover />
                            <span className="text-xs text-muted">hover: {PRODUCT_LABELS[key] ?? key}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}

export default AnimationsSandbox
