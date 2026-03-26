import '@testing-library/jest-dom'

import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BindLogic, Provider } from 'kea'

import { featureFlagLogic } from 'lib/logic/featureFlagLogic'
import { insightDataLogic } from 'scenes/insights/insightDataLogic'
import { insightLogic } from 'scenes/insights/insightLogic'
import { insightVizDataLogic } from 'scenes/insights/insightVizDataLogic'

import { useMocks } from '~/mocks/jest'
import { LifecycleQuery, NodeKind, StickinessQuery, TrendsQuery } from '~/queries/schema/schema-general'
import { initKeaTests } from '~/test/init'
import { BaseMathType, InsightShortId } from '~/types'

import { EditorFilters } from './EditorFilters'

const Insight123 = '123' as InsightShortId
const insightProps = { dashboardItemId: Insight123 }

function makeTrendsQuery(overrides?: Partial<TrendsQuery>): TrendsQuery {
    return {
        kind: NodeKind.TrendsQuery,
        series: [
            {
                kind: NodeKind.EventsNode,
                name: '$pageview',
                event: '$pageview',
                math: BaseMathType.TotalCount,
            },
        ],
        ...overrides,
    }
}

function makeLifecycleQuery(): LifecycleQuery {
    return {
        kind: NodeKind.LifecycleQuery,
        series: [
            {
                kind: NodeKind.EventsNode,
                name: '$pageview',
                event: '$pageview',
                math: BaseMathType.TotalCount,
            },
        ],
    }
}

function makeStickinessQuery(): StickinessQuery {
    return {
        kind: NodeKind.StickinessQuery,
        series: [
            {
                kind: NodeKind.EventsNode,
                name: '$pageview',
                event: '$pageview',
                math: BaseMathType.TotalCount,
            },
        ],
    }
}

function setupAndRender(query: TrendsQuery | LifecycleQuery | StickinessQuery): ReturnType<typeof insightVizDataLogic> {
    insightLogic(insightProps).mount()
    insightDataLogic(insightProps).mount()
    const vizDataLogic = insightVizDataLogic(insightProps)
    vizDataLogic.mount()
    vizDataLogic.actions.updateQuerySource(query)

    render(
        <Provider>
            <BindLogic logic={insightLogic} props={insightProps}>
                <EditorFilters query={query} showing={true} embedded={false} />
            </BindLogic>
        </Provider>
    )

    return vizDataLogic
}

describe('EditorFilters', () => {
    beforeEach(() => {
        jest.useFakeTimers()
        useMocks({
            get: {
                '/api/environments/:team_id/insights/trend': [],
                '/api/environments/:team_id/insights/': { results: [{}] },
            },
        })
        initKeaTests()
        featureFlagLogic().mount()
    })

    afterEach(() => {
        jest.useRealTimers()
        cleanup()
    })

    it('toggling formula mode switches the label between Series and Variables', async () => {
        const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
        setupAndRender(makeTrendsQuery())

        expect(screen.getByText('Series')).toBeInTheDocument()
        expect(screen.getByText('Enable formula mode')).toBeInTheDocument()

        await user.click(screen.getByText('Enable formula mode'))

        expect(screen.getByText('Variables')).toBeInTheDocument()
        expect(screen.getByText('Disable formula mode')).toBeInTheDocument()

        await user.click(screen.getByText('Disable formula mode'))

        expect(screen.getByText('Series')).toBeInTheDocument()
        expect(screen.getByText('Enable formula mode')).toBeInTheDocument()
    })

    it('unchecking a lifecycle toggle updates the query filter', async () => {
        const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
        const vizDataLogic = setupAndRender(makeLifecycleQuery())

        const dormantCheckbox = screen.getByRole('checkbox', { name: 'dormant' })
        expect(dormantCheckbox).toBeChecked()

        await user.click(dormantCheckbox)

        // Flush the 300ms debounce in updateInsightFilter
        await act(async () => {
            jest.advanceTimersByTime(500)
        })

        await waitFor(() => {
            const filter = vizDataLogic.values.lifecycleFilter
            expect(filter?.toggledLifecycles).toEqual(expect.arrayContaining(['new', 'returning', 'resurrecting']))
            expect(filter?.toggledLifecycles).not.toContain('dormant')
        })
    })

    it('re-checking a lifecycle toggle adds it back', async () => {
        const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
        const vizDataLogic = setupAndRender(makeLifecycleQuery())

        const dormantCheckbox = screen.getByRole('checkbox', { name: 'dormant' })

        // Uncheck dormant
        await user.click(dormantCheckbox)
        await act(async () => {
            jest.advanceTimersByTime(500)
        })

        await waitFor(() => {
            expect(vizDataLogic.values.lifecycleFilter?.toggledLifecycles).not.toContain('dormant')
        })

        // Re-check dormant
        await user.click(dormantCheckbox)
        await act(async () => {
            jest.advanceTimersByTime(500)
        })

        await waitFor(() => {
            expect(vizDataLogic.values.lifecycleFilter?.toggledLifecycles).toContain('dormant')
        })
    })

    it('expanding Advanced options reveals goal lines, collapsing hides them', async () => {
        const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
        setupAndRender(makeTrendsQuery())

        // Advanced options is collapsed by default
        const advancedButton = screen.getByTestId('editor-filter-group-collapse-advanced-options')
        expect(screen.queryByText('Goal lines')).not.toBeInTheDocument()

        await user.click(advancedButton)
        expect(screen.getByText('Goal lines')).toBeInTheDocument()

        await user.click(advancedButton)
        expect(screen.queryByText('Goal lines')).not.toBeInTheDocument()
    })

    it('changing stickiness computation mode updates the query', async () => {
        const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
        const vizDataLogic = setupAndRender(makeStickinessQuery())

        const select = screen.getByTestId('stickiness-mode-select')
        await user.click(select)
        await user.click(screen.getByText('Cumulative'))

        await act(async () => {
            jest.advanceTimersByTime(500)
        })

        await waitFor(() => {
            expect(vizDataLogic.values.stickinessFilter?.computedAs).toBe('cumulative')
        })
    })

    it('renders nothing when showing is false', () => {
        insightLogic(insightProps).mount()
        insightDataLogic(insightProps).mount()
        const vizDataLogic = insightVizDataLogic(insightProps)
        vizDataLogic.mount()
        vizDataLogic.actions.updateQuerySource(makeTrendsQuery())

        const { container } = render(
            <Provider>
                <BindLogic logic={insightLogic} props={insightProps}>
                    <EditorFilters query={makeTrendsQuery()} showing={false} embedded={false} />
                </BindLogic>
            </Provider>
        )

        expect(container.innerHTML).toBe('')
    })
})
