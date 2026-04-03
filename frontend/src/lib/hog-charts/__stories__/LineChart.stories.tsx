import type { Meta, StoryObj } from '@storybook/react'

import { LineChart, type LineChartProps } from '../charts/LineChart'
import type { ChartTheme, GoalLine, LineChartConfig, Series } from '../core/types'

const theme: ChartTheme = {
    colors: ['#1d4aff', '#cd0f74', '#43827e', '#621da6', '#f04f58', '#e09b2b'],
    backgroundColor: '#ffffff',
    axisColor: '#999',
    gridColor: 'rgba(0,0,0,0.08)',
    crosshairColor: '#888',
}

const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function makeSeries(key: string, data: number[], overrides?: Partial<Series>): Series {
    return { key, label: key, data, color: '', ...overrides }
}

const meta: Meta<LineChartProps> = {
    title: 'Charts/LineChart',
    component: LineChart,
    render: (args) => (
        <div style={{ width: '100%', height: 300 }}>
            <LineChart {...args} />
        </div>
    ),
    args: {
        theme,
    },
}
export default meta

type Story = StoryObj<LineChartProps>

export const SingleSeries: Story = {
    args: {
        labels: dayLabels,
        series: [makeSeries('Pageviews', [120, 95, 140, 180, 160, 90, 110])],
    },
}

export const MultipleSeries: Story = {
    args: {
        labels: dayLabels,
        series: [
            makeSeries('Pageviews', [120, 95, 140, 180, 160, 90, 110]),
            makeSeries('Signups', [30, 25, 45, 50, 40, 20, 35]),
            makeSeries('Purchases', [5, 8, 12, 15, 10, 4, 7]),
        ],
    },
}

export const DashedLine: Story = {
    args: {
        labels: dayLabels,
        series: [
            makeSeries('Actual', [120, 95, 140, 180, 160, 90, 110]),
            makeSeries('Forecast', [130, 100, 150, 170, 155, 100, 120], {
                dashPattern: [6, 4],
            }),
        ],
    },
}

export const WithDataPoints: Story = {
    args: {
        labels: dayLabels,
        series: [makeSeries('Events', [50, 80, 65, 90, 75, 45, 60], { pointRadius: 4 })],
    },
}

export const AreaFill: Story = {
    args: {
        labels: dayLabels,
        series: [makeSeries('Traffic', [120, 95, 140, 180, 160, 90, 110], { fillArea: true, fillOpacity: 0.3 })],
    },
}

export const StackedAreas: Story = {
    args: {
        labels: dayLabels,
        series: [
            makeSeries('Direct', [40, 30, 50, 60, 45, 35, 40], { fillArea: true, fillOpacity: 0.4 }),
            makeSeries('Organic', [30, 25, 35, 40, 30, 20, 25], { fillArea: true, fillOpacity: 0.4 }),
            makeSeries('Referral', [10, 15, 20, 25, 15, 10, 12], { fillArea: true, fillOpacity: 0.4 }),
        ],
    },
}

export const WithGrid: Story = {
    args: {
        labels: dayLabels,
        series: [makeSeries('Pageviews', [120, 95, 140, 180, 160, 90, 110])],
        config: { showGrid: true } satisfies LineChartConfig,
    },
}

export const WithGoalLines: Story = {
    args: {
        labels: dayLabels,
        series: [makeSeries('Revenue', [120, 95, 140, 180, 160, 90, 110])],
        config: {
            showGrid: true,
            goalLines: [
                { value: 150, label: 'Target' },
                { value: 50, label: 'Minimum', borderColor: '#f04f58' },
            ] satisfies GoalLine[],
        } satisfies LineChartConfig,
    },
}

export const WithCrosshair: Story = {
    args: {
        labels: dayLabels,
        series: [
            makeSeries('Pageviews', [120, 95, 140, 180, 160, 90, 110]),
            makeSeries('Signups', [30, 25, 45, 50, 40, 20, 35]),
        ],
        config: { showCrosshair: true, showGrid: true } satisfies LineChartConfig,
    },
}

export const LogScale: Story = {
    args: {
        labels: dayLabels,
        series: [makeSeries('Events', [1, 10, 100, 1000, 500, 50, 5])],
        config: { yScaleType: 'log', showGrid: true } satisfies LineChartConfig,
    },
}

export const PercentStack: Story = {
    args: {
        labels: dayLabels,
        series: [
            makeSeries('Chrome', [60, 55, 58, 62, 59, 57, 61], { fillArea: true }),
            makeSeries('Firefox', [20, 25, 22, 18, 21, 23, 19], { fillArea: true }),
            makeSeries('Safari', [20, 20, 20, 20, 20, 20, 20], { fillArea: true }),
        ],
        config: { percentStackView: true, showGrid: true } satisfies LineChartConfig,
    },
}

export const GapsInData: Story = {
    args: {
        labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug'],
        series: [
            makeSeries('Metric', [40, 60, NaN, NaN, 80, 100, 70, 50]),
            makeSeries('Baseline', [30, 35, 40, 45, 50, 55, 50, 45]),
        ],
        config: { showGrid: true } satisfies LineChartConfig,
    },
}

export const SingleDataPoint: Story = {
    args: {
        labels: ['Today'],
        series: [makeSeries('Events', [42], { pointRadius: 5 })],
    },
}

export const AllZeros: Story = {
    args: {
        labels: dayLabels,
        series: [makeSeries('Nothing', [0, 0, 0, 0, 0, 0, 0])],
        config: { showGrid: true } satisfies LineChartConfig,
    },
}

export const NegativeValues: Story = {
    args: {
        labels: dayLabels,
        series: [makeSeries('Delta', [-20, 15, -5, 30, -10, 25, -15])],
        config: { showGrid: true } satisfies LineChartConfig,
    },
}

export const LargeDataset: Story = {
    args: {
        labels: Array.from({ length: 90 }, (_, i) => `Day ${i + 1}`),
        series: [
            makeSeries(
                'Trend',
                Array.from({ length: 90 }, (_, i) => Math.sin(i / 5) * 50 + 100 + Math.random() * 20)
            ),
        ],
        config: {
            showGrid: true,
            xTickFormatter: (_, i) => (i % 10 === 0 ? `Day ${i + 1}` : null),
        } satisfies LineChartConfig,
    },
}

export const HiddenSeries: Story = {
    args: {
        labels: dayLabels,
        series: [
            makeSeries('Visible', [120, 95, 140, 180, 160, 90, 110]),
            makeSeries('Hidden', [500, 600, 700, 800, 900, 1000, 1100], { hidden: true }),
        ],
        config: { showGrid: true } satisfies LineChartConfig,
    },
}

export const HiddenAxes: Story = {
    args: {
        labels: dayLabels,
        series: [makeSeries('Sparkline', [120, 95, 140, 180, 160, 90, 110], { fillArea: true, fillOpacity: 0.2 })],
        config: { hideXAxis: true, hideYAxis: true } satisfies LineChartConfig,
    },
}

export const CustomFormatters: Story = {
    args: {
        labels: dayLabels,
        series: [makeSeries('Revenue', [1200, 950, 1400, 1800, 1600, 900, 1100])],
        config: {
            showGrid: true,
            yTickFormatter: (v) => `$${(v / 1000).toFixed(1)}k`,
        } satisfies LineChartConfig,
    },
}
