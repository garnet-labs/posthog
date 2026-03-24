import type { LazyAnimationFactory } from './types'

export const animationRegistry: Record<string, LazyAnimationFactory> = {
    _fallback: () => import('./animations/FallbackAnimation'),

    // Core analytics
    product_analytics: () => import('./animations/ProductAnalyticsAnimation'),
    web_analytics: () => import('./animations/WebAnalyticsAnimation'),
    session_replay: () => import('./animations/SessionReplayAnimation'),
    feature_flags: () => import('./animations/FeatureFlagsAnimation'),
    experiments: () => import('./animations/ExperimentsAnimation'),
    surveys: () => import('./animations/SurveysAnimation'),

    // Data tools
    data_warehouse: () => import('./animations/DataWarehouseAnimation'),
    pipeline: () => import('./animations/DataPipelinesAnimation'),
    hog_ql: () => import('./animations/SqlAnimation'),

    // Error & monitoring
    error_tracking: () => import('./animations/ErrorTrackingAnimation'),
    logs: () => import('./animations/LogsAnimation'),

    // AI
    llm_observability: () => import('./animations/LlmObservabilityAnimation'),
}
