import type { Meta, StoryObj } from '@storybook/react-vite'

import { Bold, Italic, Underline } from 'lucide-react'
import { ToggleGroup, ToggleGroupItem } from './toggle-group'

const meta = {
    title: 'Primitives/Toggle Group',
    component: ToggleGroup,
    tags: ['autodocs'],
} satisfies Meta<typeof ToggleGroup>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
    render: () => {
        return (
            <ToggleGroup variant="outline" multiple>
                <ToggleGroupItem value="bold" aria-label="Toggle bold" size='icon'>
                    <Bold />
                </ToggleGroupItem>
                <ToggleGroupItem value="italic" aria-label="Toggle italic" size='icon'>
                    <Italic />
                </ToggleGroupItem>
                <ToggleGroupItem value="strikethrough" aria-label="Toggle strikethrough" size='icon'>
                    <Underline />
                </ToggleGroupItem>
            </ToggleGroup>
        )
    },
} satisfies Story

export const Spacing: Story = {
    render: () => {
        return (
            <ToggleGroup variant="outline" multiple spacing={2}>
                <ToggleGroupItem value="bold" aria-label="Toggle bold" size='icon'>
                    <Bold />
                </ToggleGroupItem>
                <ToggleGroupItem value="italic" aria-label="Toggle italic" size='icon'>
                    <Italic />
                </ToggleGroupItem>
                <ToggleGroupItem value="strikethrough" aria-label="Toggle strikethrough" size='icon'>
                    <Underline />
                </ToggleGroupItem>
            </ToggleGroup>
        )
    },
} satisfies Story
