/**
 * Multivariate **`test`** = experiment (star only, no pin). **`control`** and flag off = legacy (pin only, no star).
 */
export type DashboardFavoritesExperimentVariant = 'control' | 'test'

export function getDashboardFavoritesExperimentVariant(
    flagValue: boolean | string | undefined
): DashboardFavoritesExperimentVariant {
    if (flagValue === 'test') {
        return 'test'
    }
    return 'control'
}
