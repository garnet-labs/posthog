import { render } from '@testing-library/react'
import { useState } from 'react'

import { featureFlagLogic } from 'lib/logic/featureFlagLogic'

import { actionsModel } from '~/models/actionsModel'
import { groupsModel } from '~/models/groupsModel'
import { InsightVizNode, NodeKind, TrendsQuery } from '~/queries/schema/schema-general'

import { initKeaTests } from '../init'
import { resetAllCapturedCharts } from './captured-charts'
import { resetCapturedCharts } from './chartjs-mock'
import { setupInsightMocks, type SetupMocksOptions } from './mocks'

export const INSIGHT_TEST_KEY = 'test-harness'
export const INSIGHT_TEST_ID = `new-AdHoc.InsightViz.${INSIGHT_TEST_KEY}`

export function buildTrendsQuery(overrides?: Partial<TrendsQuery>): TrendsQuery {
    return {
        kind: NodeKind.TrendsQuery,
        series: [{ kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' }],
        ...overrides,
    }
}

/** Sets up Kea context, mounts common logics, and configures insight API mocks. */
function setupTestEnvironment(mocks?: SetupMocksOptions, featureFlags?: Record<string, string | boolean>): void {
    resetAllCapturedCharts()
    resetCapturedCharts()

    initKeaTests()
    actionsModel.mount()
    groupsModel.mount()

    // Always mount featureFlagLogic. Components hanging off the full insight
    // pipeline (e.g. hog-charts bridges reading themeLogic) transitively read
    // feature flags during render, and leaving this logic unmounted causes
    // "Can not find path lib.logic.featureFlagLogic in the store" errors.
    const ffLogic = featureFlagLogic()
    ffLogic.mount()
    // Call setFeatureFlags even without overrides so the reducer seeds an empty
    // map and the selector never throws on first read.
    ffLogic.actions.setFeatureFlags(
        Object.keys(featureFlags ?? {}),
        (featureFlags ?? {}) as Record<string, string | boolean>
    )

    setupInsightMocks(mocks)
}

export interface RenderWithInsightsProps {
    component: React.ReactElement
    mocks?: SetupMocksOptions
    featureFlags?: Record<string, string | boolean>
}

/** Render any component with insight mocks and Kea logics ready. */
export function renderWithInsights(props: RenderWithInsightsProps): ReturnType<typeof render> {
    setupTestEnvironment(props.mocks, props.featureFlags)
    return render(props.component)
}

export interface RenderInsightPageProps {
    query?: TrendsQuery
    showFilters?: boolean
    mocks?: SetupMocksOptions
    featureFlags?: Record<string, string | boolean>
}

function InsightWrapper({ query, showFilters = false }: { query: TrendsQuery; showFilters: boolean }): JSX.Element {
    const [vizQuery, setVizQuery] = useState<InsightVizNode>({
        kind: NodeKind.InsightVizNode,
        source: query,
        showFilters,
        showHeader: showFilters,
        full: showFilters,
    })

    // Dynamic require to break a circular-dependency cycle that causes Jest to fail
    // with static imports. Node's module cache means this is only resolved once.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { InsightViz } = require('~/queries/nodes/InsightViz/InsightViz')

    return <InsightViz uniqueKey={INSIGHT_TEST_KEY} query={vizQuery} setQuery={setVizQuery} />
}

export function renderInsightPage(props: RenderInsightPageProps = {}): ReturnType<typeof render> {
    setupTestEnvironment(props.mocks, props.featureFlags)

    return render(<InsightWrapper query={props.query ?? buildTrendsQuery()} showFilters={props.showFilters ?? true} />)
}
