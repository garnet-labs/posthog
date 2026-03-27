import { render } from '@testing-library/react'

import { Exporter } from '~/exporter/Exporter'
import { ExportType, ExportedData } from '~/exporter/types'
import { HogQLVariable } from '~/queries/schema/schema-general'
import { initKeaTests } from '~/test/init'

// Mock ExportedInsight so we can inspect props without needing full kea/Query setup
const mockExportedInsight = jest.fn(() => <div data-testid="exported-insight" />)
jest.mock('~/exporter/ExportedInsight/ExportedInsight', () => ({
    ExportedInsight: (props: any) => mockExportedInsight(props),
}))

beforeEach(() => {
    initKeaTests()
    mockExportedInsight.mockClear()
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

function makeInsightExport(overrides: Partial<ExportedData> = {}): ExportedData {
    return {
        type: ExportType.Image,
        insight: {
            id: 42,
            short_id: 'abc123',
            name: 'Test Insight',
            query: { kind: 'TrendsQuery', series: [{ event: '$pageview' }] },
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

describe('Exporter (insight with variables_override)', () => {
    it('passes variables_override to ExportedInsight when present', () => {
        const variablesOverride: Record<string, HogQLVariable> = {
            var1: { variableId: 'var1', code_name: 'region', value: 'EU' },
        }

        render(<Exporter {...makeInsightExport({ variables_override: variablesOverride })} />)

        expect(mockExportedInsight).toHaveBeenCalledWith(
            expect.objectContaining({
                variablesOverride: variablesOverride,
            })
        )
    })

    it('passes undefined variablesOverride when no variables_override in data', () => {
        render(<Exporter {...makeInsightExport()} />)

        expect(mockExportedInsight).toHaveBeenCalledWith(
            expect.objectContaining({
                variablesOverride: undefined,
            })
        )
    })

    it('renders ExportedInsight component for insight exports', () => {
        render(<Exporter {...makeInsightExport()} />)

        expect(mockExportedInsight).toHaveBeenCalled()
    })
})
