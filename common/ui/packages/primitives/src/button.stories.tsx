import type { Meta, StoryObj } from '@storybook/react-vite'
import { TrashIcon } from 'lucide-react'

import { Button } from './button'

const meta = {
    title: 'Primitives/Button',
    component: Button,
    tags: ['autodocs'],
    argTypes: {
        variant: {
            control: 'select',
            options: ['default', 'outline', 'secondary', 'ghost', 'destructive', 'link'],
        },
        size: {
            control: 'select',
            options: ['default', 'xs', 'sm', 'lg', 'icon', 'icon-xs', 'icon-sm', 'icon-lg'],
        },
        disabled: { control: 'boolean' },
    },
} satisfies Meta<typeof Button>

export default meta
type Story = StoryObj<typeof meta>

export const Default = {
    render: () => (
        <div className="flex flex-wrap gap-2">
            <Button variant="default">Default</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="destructive">Destructive</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="link">Link</Button>
        </div>
    ),
} satisfies Story

export const WithIcons = {
    render: () => (
        <div className="flex flex-wrap gap-2">
            <Button variant="default">
                <TrashIcon /> Default
            </Button>
            <Button variant="outline">
                <TrashIcon /> Outline
            </Button>
            <Button variant="destructive">
                <TrashIcon /> Destructive
            </Button>
            <Button variant="ghost">
                <TrashIcon /> Ghost
            </Button>
            <Button variant="link">
                <TrashIcon /> Link
            </Button>
        </div>
    ),
} satisfies Story

export const IconOnly = {
    render: () => (
        <div className="flex flex-wrap gap-2">
            <Button variant="default" size="icon">
                <TrashIcon />
            </Button>
            <Button variant="outline" size="icon">
                <TrashIcon />
            </Button>
            <Button variant="destructive" size="icon">
                <TrashIcon />
            </Button>
            <Button variant="ghost" size="icon">
                <TrashIcon />
            </Button>
            <Button variant="link" size="icon">
                <TrashIcon />
            </Button>
        </div>
    ),
} satisfies Story

export const Sizes = {
    render: () => (
        <div className="flex items-center gap-2">
            <Button size="lg">Large</Button>
            <Button size="icon-lg">
                <TrashIcon />
            </Button>
            <Button size="default">Default</Button>
            <Button size="icon">
                <TrashIcon />
            </Button>
            <Button size="sm">Small</Button>
            <Button size="icon-sm">
                <TrashIcon />
            </Button>
            <Button size="xs">Extra small</Button>
            <Button size="icon-xs">
                <TrashIcon />
            </Button>
        </div>
    ),
} satisfies Story

export const Disabled = {
    render: () => (
        <div className="flex items-center gap-2">
            <Button variant="default" disabled>
                Default
            </Button>
            <Button variant="outline" disabled>
                Outline
            </Button>
            <Button variant="destructive" disabled>
                Destructive
            </Button>
            <Button variant="ghost" disabled>
                Ghost
            </Button>
            <Button variant="link" disabled>
                Link
            </Button>
        </div>
    ),
} satisfies Story
