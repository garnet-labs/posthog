import { samplePersonProperties, sampleRetentionPeopleResponse } from 'scenes/insights/__mocks__/insight.mocks'

import { Meta, StoryFn, StoryObj } from '@storybook/react'
import { router } from 'kea-router'

import { useOnMountEffect } from 'lib/hooks/useOnMountEffect'
import { App } from 'scenes/App'
import { createInsightStory } from 'scenes/insights/__mocks__/createInsightScene'

import { mswDecorator, useStorybookMocks } from '~/mocks/browser'

import worldMapInsight from '../../../../mocks/fixtures/api/projects/team_id/insights/trendsWorldMap.json'

type Story = StoryObj<typeof App>
const meta: Meta = {
    title: 'Scenes-App/Insights/WorldMap',
    parameters: {
        layout: 'fullscreen',
        testOptions: {
            snapshotBrowsers: ['chromium'],
            viewport: {
                width: 1300,
                height: 720,
            },
        },
        viewMode: 'story',
        mockDate: '2022-04-05',
    },
    decorators: [
        mswDecorator({
            get: {
                '/api/environments/:team_id/persons/retention': sampleRetentionPeopleResponse,
                '/api/environments/:team_id/persons/properties': samplePersonProperties,
                '/api/projects/:team_id/groups_types': [],
            },
            post: {
                '/api/projects/:team_id/cohorts/': { id: 1 },
            },
        }),
    ],
}
export default meta

export const Default: Story = createInsightStory(
    require('../../../../mocks/fixtures/api/projects/team_id/insights/trendsWorldMap.json')
)
Default.parameters = { testOptions: { waitForSelector: '.WorldMap' } }

export const WorldMapEmpty: StoryFn = () => {
    useStorybookMocks({
        get: {
            '/api/environments/:team_id/insights/': (_, __, ctx) => [
                ctx.delay(100),
                ctx.status(200),
                ctx.json({ count: 1, results: [{ ...worldMapInsight, result: [] }] }),
            ],
        },
        post: {
            '/api/environments/:team_id/query/': (_, __, ctx) => [
                ctx.status(200),
                ctx.json({
                    results: [],
                    is_cached: true,
                }),
            ],
        },
    })

    useOnMountEffect(() => {
        router.actions.push(`/insights/${worldMapInsight.short_id}`)
    })

    return <App />
}
WorldMapEmpty.parameters = {
    testOptions: {
        waitForSelector: '.WorldMap',
    },
}

export const WorldMapError: StoryFn = () => {
    useStorybookMocks({
        get: {
            '/api/environments/:team_id/insights/': (_, __, ctx) => [
                ctx.delay(100),
                ctx.status(200),
                ctx.json({ count: 1, results: [{ ...worldMapInsight, result: null }] }),
            ],
        },
        post: {
            '/api/environments/:team_id/query/': (_, __, ctx) => [
                ctx.delay(100),
                ctx.status(500),
                ctx.json({
                    type: 'server_error',
                    detail: 'There is nothing you can do to stop the impending catastrophe.',
                }),
            ],
        },
    })

    useOnMountEffect(() => {
        router.actions.push(`/insights/${worldMapInsight.short_id}`)
    })

    return <App />
}
WorldMapError.parameters = {
    testOptions: {
        waitForSelector: '[data-attr="insight-retry-button"]',
    },
}

export const WorldMapLoading: StoryFn = () => {
    useStorybookMocks({
        get: {
            '/api/environments/:team_id/insights/': (_, __, ctx) => [
                ctx.status(200),
                ctx.json({ count: 1, results: [{ ...worldMapInsight, result: null }] }),
            ],
        },
        post: {
            '/api/environments/:team_id/query/': (_, __, ctx) => [ctx.delay('infinite')],
        },
    })

    useOnMountEffect(() => {
        router.actions.push(`/insights/${worldMapInsight.short_id}`)
    })

    return <App />
}
WorldMapLoading.parameters = {
    testOptions: {
        waitForLoadersToDisappear: false,
    },
}
