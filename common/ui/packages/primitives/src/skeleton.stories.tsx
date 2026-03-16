import type { Meta, StoryObj } from '@storybook/react-vite'

import { Skeleton } from './skeleton'

const meta = {
    title: 'Primitives/Skeleton',
    component: Skeleton,
    tags: ['autodocs'],
} satisfies Meta<typeof Skeleton>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
    render: () => (
        <div className="flex flex-col gap-2">
            <div className="grid grid-cols-2 gap-2 max-w-sm">
                <div className="flex flex-col gap-2 max-w-sm pt-1.5">
                    <Skeleton className="h-5.5" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight">h1 title tag</h1>
            </div>
            <div className="grid grid-cols-2 gap-2 max-w-sm">
                <div className="flex flex-col gap-2 max-w-sm pt-1.5">
                    <Skeleton className="h-4.5" />
                </div>
                <h2 className="text-xl font-bold tracking-tight">h2 title tag</h2>
            </div>
            <div className="grid grid-cols-2 gap-2 max-w-sm">
                <div className="flex flex-col gap-2 max-w-sm pt-2">
                    <Skeleton className="h-3.5" />
                </div>
                <h3 className="text-lg font-bold tracking-tight">h3 title tag</h3>
            </div>
        </div>
    ),
} satisfies Story

export const Paragraph: Story = {
    render: () => (
        <div className="grid grid-cols-2 gap-2 max-w-sm">
            <div className="flex flex-col gap-2 max-w-sm pt-1.5">
                <Skeleton className="h-4" />
                <Skeleton className="h-4" />
                <Skeleton className="h-4" />
                <Skeleton className="h-4" />
            </div>
            <p>paragraph text, very nuanced and complex to replicate with loading states, just do your best</p>
        </div>
    ),
} satisfies Story
