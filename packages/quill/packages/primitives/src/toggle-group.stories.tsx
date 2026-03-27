import type { Meta, StoryObj } from '@storybook/react-vite'

import { Bold, Italic, Underline } from 'lucide-react'
import { ToggleGroup, ToggleGroupItem } from './toggle-group'
import { Button } from './button'

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
            <div className="flex gap-2">
                <ToggleGroup variant="outline" multiple>
                    <ToggleGroupItem value="bold" aria-label="Toggle bold">
                        <Bold />
                    </ToggleGroupItem>
                    <ToggleGroupItem value="italic" aria-label="Toggle italic">
                        <Italic />
                    </ToggleGroupItem>
                    <ToggleGroupItem value="strikethrough" aria-label="Toggle strikethrough">
                        <Underline />
                    </ToggleGroupItem>
                </ToggleGroup>
                <ToggleGroup variant="outline" multiple size='sm'>
                    <ToggleGroupItem value="bold" aria-label="Toggle bold">
                        <Bold />
                    </ToggleGroupItem>
                    <ToggleGroupItem value="italic" aria-label="Toggle italic">
                        <Italic />
                    </ToggleGroupItem>
                    <ToggleGroupItem value="strikethrough" aria-label="Toggle strikethrough">
                        <Underline />
                    </ToggleGroupItem>
                </ToggleGroup>
                <ToggleGroup variant="outline" multiple size='lg'>
                    <ToggleGroupItem value="bold" aria-label="Toggle bold">
                        <Bold />
                    </ToggleGroupItem>
                    <ToggleGroupItem value="italic" aria-label="Toggle italic">
                        <Italic />
                    </ToggleGroupItem>
                    <ToggleGroupItem value="strikethrough" aria-label="Toggle strikethrough">
                        <Underline />
                    </ToggleGroupItem>
                </ToggleGroup>
            </div>
        )
    },
} satisfies Story
