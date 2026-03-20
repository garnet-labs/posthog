import type { Meta, StoryObj } from '@storybook/react-vite'

import { Input } from './input'

const meta = {
    title: 'Primitives/Input',
    component: Input,
    tags: ['autodocs'],
} satisfies Meta<typeof Input>

export default meta
type Story = StoryObj<typeof meta>


export const Default: Story = {
    render: () => (
        <div className="flex flex-col gap-2">
            <Input placeholder="Enter your email" />
            <Input placeholder="Enter your password" type="password" />
            <Input placeholder="Enter your email" disabled />
            <Input placeholder="Enter your email" aria-invalid />
        </div>
    ),
} satisfies Story
