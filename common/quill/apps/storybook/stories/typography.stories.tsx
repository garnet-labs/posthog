import type { Meta, StoryObj } from '@storybook/react-vite'

const meta = {
    title: 'Tokens/Typography',
    tags: ['autodocs'],
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
    render: () => {
        return (
            <div className="space-y-6">
                <h1 className="text-2xl font-bold">Heading 1</h1>
                <h2 className="text-xl font-bold">Heading 2</h2>
                <h3 className="text-lg font-bold">Heading 3</h3>
                <h4 className="text-base font-bold">Heading 4</h4>
                <h5 className="text-sm font-bold">Heading 5</h5>
                <p className="text-base">Paragraph</p>
                <p className="text-xs">Fine print</p>
                <small className="text-xxs">Small</small>
            </div>
        )
    },
}
