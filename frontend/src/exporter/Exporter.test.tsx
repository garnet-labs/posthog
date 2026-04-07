import '@testing-library/jest-dom'

import { render } from '@testing-library/react'

import { Exporter } from '~/exporter/Exporter'
import { ExportType, ExportedData } from '~/exporter/types'
import { initKeaTests } from '~/test/init'

// Mock NodeWrapper to avoid circular dependencies
jest.mock('scenes/notebooks/Nodes/NodeWrapper', () => ({
    createPostHogWidgetNode: jest.fn(() => ({})),
}))

// Mock maplibre-gl to avoid window.URL.createObjectURL issues
jest.mock('maplibre-gl', () => ({
    __esModule: true,
    default: {
        Marker: jest.fn(),
        Map: jest.fn(),
        NavigationControl: jest.fn(),
        addProtocol: jest.fn(),
    },
    Marker: jest.fn(),
    Map: jest.fn(),
    NavigationControl: jest.fn(),
    addProtocol: jest.fn(),
}))

beforeEach(() => {
    initKeaTests()
})

function makeDashboardExport(overrides: Partial<ExportedData> = {}): ExportedData {
    return {
        type: ExportType.Scene,
        dashboard: {
            id: 123,
            name: 'My shared dashboard',
            description: 'Description',
            tags: [],
            tiles: [],
        } as any,
        themes: [],
        ...overrides,
    }
}

describe('Exporter (shared dashboard)', () => {
    it('sets document title with PostHog suffix by default', () => {
        const initialTitle = document.title

        render(<Exporter {...makeDashboardExport()} />)

        expect(document.title).toBe('My shared dashboard • PostHog')

        // restore to avoid leaking between tests
        document.title = initialTitle
    })

    it('omits PostHog suffix from title when whitelabel is enabled', () => {
        const initialTitle = document.title

        render(<Exporter {...makeDashboardExport({ whitelabel: true })} />)

        expect(document.title).toBe('My shared dashboard')

        document.title = initialTitle
    })

    it('shows auto refresh text in header', () => {
        const { getAllByRole, getAllByText } = render(<Exporter {...makeDashboardExport()} />)

        // The dashboard header can be rendered multiple times depending on internal
        // export layout/portal behavior.
        const headings = getAllByRole('heading', { name: 'My shared dashboard' })
        expect(headings.length).toBeGreaterThan(0)
        expect(getAllByText(/Auto refresh every/i).length).toBeGreaterThan(0)
    })

    it('does not show auto refresh text for image exports', () => {
        const { container } = render(<Exporter {...makeDashboardExport({ type: ExportType.Image })} />)

        // Image exports use a minimal header (h1 + description), not the Scene header with "Auto refresh every"
        expect(container.querySelector('.SharedDashboard-header')).toBeNull()
    })
})
