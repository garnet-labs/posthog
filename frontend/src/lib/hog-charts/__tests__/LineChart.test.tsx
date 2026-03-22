import '@testing-library/jest-dom'

import { render } from '@testing-library/react'

import { LineChart } from '../components/LineChart'

// Mock ResizeObserver
beforeAll(() => {
    global.ResizeObserver = class {
        observe = jest.fn()
        unobserve = jest.fn()
        disconnect = jest.fn()
    }
})

// Mock canvas context
HTMLCanvasElement.prototype.getContext = jest.fn().mockReturnValue({
    beginPath: jest.fn(),
    moveTo: jest.fn(),
    lineTo: jest.fn(),
    stroke: jest.fn(),
    fill: jest.fn(),
    arc: jest.fn(),
    setLineDash: jest.fn(),
    clearRect: jest.fn(),
    save: jest.fn(),
    restore: jest.fn(),
    closePath: jest.fn(),
    scale: jest.fn(),
    setTransform: jest.fn(),
    strokeStyle: '',
    fillStyle: '',
    lineWidth: 1,
    lineJoin: 'round',
    lineCap: 'round',
    globalAlpha: 1,
    canvas: { width: 800, height: 400 },
})

// Mock getComputedStyle for color resolution
Object.defineProperty(window, 'getComputedStyle', {
    value: () => ({
        getPropertyValue: () => '#1d4aff',
    }),
})

describe('LineChart', () => {
    const defaultProps = {
        series: [
            { key: 'signups', label: 'Signups', data: [10, 25, 30, 15], color: '#1d4aff' },
            { key: 'activations', label: 'Activations', data: [5, 12, 18, 10], color: '#f97316' },
        ],
        labels: ['Mon', 'Tue', 'Wed', 'Thu'],
    }

    it('renders without crashing', () => {
        const { container } = render(<LineChart {...defaultProps} />)
        expect(container.querySelector('canvas')).toBeInTheDocument()
    })

    it('renders with all overlay options enabled', () => {
        const { container } = render(
            <LineChart
                {...defaultProps}
                showGrid
                showCrosshair
                showDataLabels
                showTrendLines
                goalLines={[{ value: 20, label: 'Target' }]}
            />
        )
        expect(container.querySelector('canvas')).toBeInTheDocument()
    })

    it('renders with percent stack view', () => {
        const { container } = render(<LineChart {...defaultProps} percentStackView />)
        expect(container.querySelector('canvas')).toBeInTheDocument()
    })

    it('renders with hidden axes', () => {
        const { container } = render(<LineChart {...defaultProps} hideXAxis hideYAxis />)
        expect(container.querySelector('canvas')).toBeInTheDocument()
    })

    it('renders with custom formatters', () => {
        const { container } = render(
            <LineChart {...defaultProps} xTickFormatter={(v) => v.toUpperCase()} yTickFormatter={(v) => `${v} users`} />
        )
        expect(container.querySelector('canvas')).toBeInTheDocument()
    })

    it('renders with render prop tooltip', () => {
        const { container } = render(
            <LineChart
                {...defaultProps}
                renderTooltip={(ctx) => (
                    <div data-testid="tooltip">
                        {ctx.label}: {ctx.seriesData.length} series
                    </div>
                )}
            />
        )
        expect(container.querySelector('canvas')).toBeInTheDocument()
    })

    it('renders with incomplete data', () => {
        const { container } = render(<LineChart {...defaultProps} incompleteFromIndex={2} />)
        expect(container.querySelector('canvas')).toBeInTheDocument()
    })

    it('renders with log scale', () => {
        const { container } = render(
            <LineChart
                {...defaultProps}
                series={[{ key: 'test', label: 'Test', data: [1, 10, 100, 1000], color: '#1d4aff' }]}
                yScaleType="log"
            />
        )
        expect(container.querySelector('canvas')).toBeInTheDocument()
    })

    it('handles empty series', () => {
        const { container } = render(<LineChart series={[]} labels={[]} />)
        expect(container.querySelector('canvas')).toBeInTheDocument()
    })

    it('applies className', () => {
        const { container } = render(<LineChart {...defaultProps} className="my-chart" />)
        expect(container.querySelector('.my-chart')).toBeInTheDocument()
    })
})
