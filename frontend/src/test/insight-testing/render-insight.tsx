import { render } from '@testing-library/react'
import { BindLogic } from 'kea'
import { useState } from 'react'

import { featureFlagLogic } from 'lib/logic/featureFlagLogic'

import { actionsModel } from '~/models/actionsModel'
import { groupsModel } from '~/models/groupsModel'
import { InsightVizNode, NodeKind, TrendsQuery } from '~/queries/schema/schema-general'
import type { InsightLogicProps } from '~/types'

import { initKeaTests } from '../init'
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
    resetCapturedCharts()

    initKeaTests()
    actionsModel.mount()
    groupsModel.mount()

    if (featureFlags && Object.keys(featureFlags).length > 0) {
        const ffLogic = featureFlagLogic()
        ffLogic.mount()
        ffLogic.actions.setFeatureFlags(Object.keys(featureFlags), featureFlags)
    }

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

export interface RenderInsightVizProps {
    query?: TrendsQuery
    component: React.ComponentType<Record<string, unknown>>
    mocks?: SetupMocksOptions
    featureFlags?: Record<string, string | boolean>
}

/** Render an insight viz component (e.g. TrendInsight) with the kea logic chain
 *  wired up and API mocks in place — without the InsightViz editor/toolbar chrome.
 *  Reusable for any component that reads from insightLogic / trendsDataLogic. */
export function renderInsightViz(props: RenderInsightVizProps): ReturnType<typeof render> {
    const query = props.query ?? buildTrendsQuery()
    setupTestEnvironment(props.mocks, props.featureFlags)

    const Component = props.component
    return render(<InsightVizWrapper query={query} component={Component} />)
}

function InsightVizWrapper({
    query,
    component: Component,
}: {
    query: TrendsQuery
    component: React.ComponentType<Record<string, unknown>>
}): JSX.Element {
    const [vizQuery, setVizQuery] = useState<InsightVizNode>({
        kind: NodeKind.InsightVizNode,
        source: query,
    })

    // Dynamic requires to break circular-dependency cycles in Jest.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { insightLogic } = require('scenes/insights/insightLogic')
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { insightDataLogic } = require('scenes/insights/insightDataLogic')
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { insightVizDataLogic } = require('scenes/insights/insightVizDataLogic')
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { dataNodeLogic } = require('~/queries/nodes/DataNode/dataNodeLogic')
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { insightVizDataNodeKey, insightVizDataCollectionId } = require('~/queries/nodes/InsightViz/InsightViz')

    const insightProps: InsightLogicProps = {
        dashboardItemId: INSIGHT_TEST_ID,
        query: vizQuery,
        setQuery: setVizQuery,
    }

    const vizKey = insightVizDataNodeKey(insightProps)
    const dataNodeLogicProps = {
        query: vizQuery.source,
        key: vizKey,
        dataNodeCollectionId: insightVizDataCollectionId(insightProps, vizKey),
    }

    return (
        <BindLogic logic={insightLogic} props={insightProps}>
            <BindLogic logic={insightDataLogic} props={insightProps}>
                <BindLogic logic={dataNodeLogic} props={dataNodeLogicProps}>
                    <BindLogic logic={insightVizDataLogic} props={insightProps}>
                        <Component />
                    </BindLogic>
                </BindLogic>
            </BindLogic>
        </BindLogic>
    )
}
