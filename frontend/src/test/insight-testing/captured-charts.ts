/** Shared capture array for both Chart.js and HogLineChart mocks.
 *  Kept in its own module to avoid circular dependencies. */

export interface CapturedChartConfig {
    type?: string
    data?: {
        labels?: string[]
        datasets?: {
            label?: string
            data?: number[]
            hidden?: boolean
            count?: number
            compare?: boolean
            compare_label?: string
            status?: string
            borderColor?: string
            backgroundColor?: string
            yAxisID?: string
        }[]
    }
    options?: {
        scales?: Record<
            string,
            | {
                  display?: boolean
                  type?: string
                  stacked?: boolean
                  position?: string
                  ticks?: { callback?: (value: number | string, index: number, values: unknown[]) => string }
              }
            | undefined
        >
        [key: string]: unknown
    }
}

export interface CapturedChart {
    config: CapturedChartConfig
    canvas: HTMLCanvasElement | null
}

let capturedCharts: CapturedChart[] = []

export function resetCapturedCharts(): void {
    capturedCharts = []
}

export function pushCapturedChart(config: CapturedChartConfig, canvas: HTMLCanvasElement | null): void {
    capturedCharts.push({ config, canvas })
}

export function getCapturedCharts(): CapturedChart[] {
    return capturedCharts
}
