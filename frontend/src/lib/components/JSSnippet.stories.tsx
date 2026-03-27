import { Meta, StoryObj } from '@storybook/react'

import { mswDecorator } from '~/mocks/browser'

import { JSSnippet } from './JSSnippet'

const meta: Meta<typeof JSSnippet> = {
    title: 'Components/JSSnippet',
    component: JSSnippet,
    decorators: [
        mswDecorator({
            get: {
                '/api/organizations/:organization_id/proxy_records': [],
            },
        }),
    ],
}
export default meta

type Story = StoryObj<typeof JSSnippet>

export const Default: Story = {
    parameters: {
        testOptions: {
            snapshotBrowsers: [], // Non-deterministic width causes intermittent snapshot failures.
            // Flapping snapshots are productivity killers. Root cause: `getPosthogMethods()` reads
            // live PostHog prototype methods whose order/count varies with render timing, producing
            // snippet widths of ~17 107 px vs ~17 133 px. These snapshots have no meaningful visual
            // regression value, so they are skipped permanently. If restored, consider mocking the
            // PostHog instance in the story to produce a deterministic method list.
        },
    },
}
