import { samplePersonProperties, sampleRetentionPeopleResponse } from 'scenes/insights/__mocks__/insight.mocks'

import { Meta, StoryFn, StoryObj } from '@storybook/react'
import { router } from 'kea-router'

import { useOnMountEffect } from 'lib/hooks/useOnMountEffect'
import { App } from 'scenes/App'
import { createInsightStory } from 'scenes/insights/__mocks__/createInsightScene'

import { mswDecorator, useStorybookMocks } from '~/mocks/browser'

import retentionInsightFixture from '../../mocks/fixtures/api/projects/team_id/insights/retention.json'

const retentionInsight = retentionInsightFixture as any

type Story = StoryObj<typeof App>
const meta: Meta = {
    title: 'Scenes-App/Insights/Retention',
    parameters: {
        layout: 'fullscreen',
        testOptions: {
            snapshotBrowsers: ['chromium'],
            viewport: {
                // needs a slightly larger width to push the rendered scene away from breakpoint boundary
                width: 1300,
                height: 720,
            },
        },
        viewMode: 'story',
        mockDate: '2022-03-11',
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
/* eslint-disable @typescript-eslint/no-var-requires */

// Retention

export const Retention: Story = createInsightStory(
    require('../../mocks/fixtures/api/projects/team_id/insights/retention.json')
)
Retention.parameters = {
    testOptions: { waitForSelector: '[data-attr=trend-line-graph] > canvas' },
}
export const RetentionEdit: Story = createInsightStory(
    require('../../mocks/fixtures/api/projects/team_id/insights/retention.json'),
    'edit'
)
RetentionEdit.parameters = {
    testOptions: { waitForSelector: '[data-attr=trend-line-graph] > canvas' },
}

export const RetentionEditViewports: Story = createInsightStory(
    require('../../mocks/fixtures/api/projects/team_id/insights/retention.json'),
    'edit'
)
RetentionEditViewports.parameters = {
    testOptions: {
        waitForSelector: '[data-attr=trend-line-graph] > canvas',
        viewportWidths: ['medium', 'wide', 'superwide'],
    },
}

// Error, Empty, Loading states

export const RetentionEmpty: StoryFn = () => {
    useStorybookMocks({
        get: {
            '/api/environments/:team_id/insights/': (_, __, ctx) => [
                ctx.delay(100),
                ctx.status(200),
                ctx.json({ count: 1, results: [{ ...retentionInsight, result: [] }] }),
            ],
            '/api/environments/:team_id/persons/retention': sampleRetentionPeopleResponse,
            '/api/environments/:team_id/persons/properties': samplePersonProperties,
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
        router.actions.push(`/insights/${retentionInsight.short_id}`)
    })

    return <App />
}
RetentionEmpty.parameters = {
    testOptions: {
        waitForSelector: '[data-attr="retention-table"]',
    },
}

export const RetentionError: StoryFn = () => {
    useStorybookMocks({
        get: {
            '/api/environments/:team_id/insights/': (_, __, ctx) => [
                ctx.delay(100),
                ctx.status(200),
                ctx.json({ count: 1, results: [{ ...retentionInsight, result: null }] }),
            ],
            '/api/environments/:team_id/persons/retention': sampleRetentionPeopleResponse,
            '/api/environments/:team_id/persons/properties': samplePersonProperties,
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
        router.actions.push(`/insights/${retentionInsight.short_id}`)
    })

    return <App />
}
RetentionError.parameters = {
    testOptions: {
        waitForSelector: '[data-attr="insight-retry-button"]',
    },
}

export const RetentionLoading: StoryFn = () => {
    useStorybookMocks({
        get: {
            '/api/environments/:team_id/insights/': (_, __, ctx) => [
                ctx.status(200),
                ctx.json({ count: 1, results: [{ ...retentionInsight, result: null }] }),
            ],
            '/api/environments/:team_id/persons/retention': sampleRetentionPeopleResponse,
            '/api/environments/:team_id/persons/properties': samplePersonProperties,
        },
        post: {
            '/api/environments/:team_id/query/': (_, __, ctx) => [ctx.delay('infinite')],
        },
    })

    useOnMountEffect(() => {
        router.actions.push(`/insights/${retentionInsight.short_id}`)
    })

    return <App />
}
RetentionLoading.parameters = {
    testOptions: {
        waitForLoadersToDisappear: false,
    },
}

/* eslint-enable @typescript-eslint/no-var-requires */
