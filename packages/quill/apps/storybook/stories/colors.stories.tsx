import type { Meta, StoryObj } from '@storybook/react-vite'

import { semanticColors } from '@posthog/quill-tokens'

const meta = {
    title: 'Tokens/Colors',
    tags: ['autodocs'],
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

type ColorSwatchItem = {
    name: string
    items: ColorSwatch[]
    usages?: readonly string[]
}
type ColorSwatch = {
    className: string
    name: string
    tailwindClass: string
    value: string
}

function ColorSwatchValue({ className, name, tailwindClass, value }: ColorSwatch): React.ReactElement {
    return (
        <div className="flex gap-2 items-center">
            <div
                className={`size-16 border flex items-center justify-center ${className} rounded-sm`}
                style={{ backgroundColor: value }}
            >
                {name.includes('foreground') ? <span className="text-xs mx-auto">Aa</span> : null}
            </div>
            <div className="flex flex-col">
                <span className="font-medium">{name}</span>
                <span className="text-xs text-muted-foreground font-mono">.{tailwindClass}</span>
                <span className="text-xs text-muted-foreground font-mono">{value}</span>
            </div>
        </div>
    )
}

function ColorSwatch({ name, items, usages }: ColorSwatchItem): React.ReactElement {
    return (
        <div className="flex flex-col gap-4 mb-8">
            {name}
            <div className="grid grid-cols-[300px_300px] gap-2">
                {items[0] && <ColorSwatchValue {...items[0]} />}
                {items[1] && <ColorSwatchValue {...items[1]} />}
            </div>
            <div className="flex flex-col">
                {usages?.map((usage) => (
                    <span key={usage} className="text-xs text-muted-foreground font-mono">
                        {usage}
                    </span>
                ))}
            </div>
        </div>
    )
}

export const AllColors: Story = {
    render: () => {
        return (
            <div className="space-y-6">
                <p className="text-sm text-muted-foreground">
                    Semantic color tokens from <code className="text-xs">@posthog/quill-tokens</code>. Toggle the theme
                    in the toolbar to see dark mode values.
                </p>
                <div>
                    <ColorSwatch
                        name="Base"
                        items={[
                            {
                                className: 'bg-background',
                                name: 'background',
                                tailwindClass: 'bg-background',
                                value: semanticColors.background[0],
                            },
                            {
                                className: 'text-foreground',
                                name: 'foreground',
                                tailwindClass: 'text-foreground',
                                value: semanticColors.foreground[0],
                            },
                        ]}
                        usages={['Main background of the app']}
                    />
                    <ColorSwatch
                        name="Card"
                        items={[
                            {
                                className: 'bg-card',
                                name: 'card',
                                tailwindClass: 'bg-card',
                                value: semanticColors.card[0],
                            },
                            {
                                className: 'text-card-foreground',
                                name: 'card-foreground',
                                tailwindClass: 'text-card-foreground',
                                value: semanticColors['card-foreground'][0],
                            },
                        ]}
                        usages={['Background of cards and other surfaces like, modals, charts, etc.']}
                    />
                    <ColorSwatch
                        name="Popover"
                        items={[
                            {
                                className: 'bg-popover',
                                name: 'popover',
                                tailwindClass: 'bg-popover',
                                value: semanticColors.popover[0],
                            },
                            {
                                className: 'text-popover-foreground',
                                name: 'popover-foreground',
                                tailwindClass: 'text-popover-foreground',
                                value: semanticColors['popover-foreground'][0],
                            },
                        ]}
                        usages={['Background of popovers and other surfaces like, tooltips, dropdowns, etc.']}
                    />

                    <ColorSwatch
                        name="Primary"
                        items={[
                            {
                                className: 'bg-primary',
                                name: 'primary',
                                tailwindClass: 'bg-primary',
                                value: semanticColors.primary[0],
                            },
                            {
                                className: 'text-primary-foreground',
                                name: 'primary-foreground',
                                tailwindClass: 'text-primary-foreground',
                                value: semanticColors['primary-foreground'][0],
                            },
                        ]}
                        usages={['Main background of the app']}
                    />

                    <ColorSwatch
                        name="Secondary"
                        items={[
                            {
                                className: 'bg-secondary',
                                name: 'secondary',
                                tailwindClass: 'bg-secondary',
                                value: semanticColors.secondary[0],
                            },
                            {
                                className: 'text-secondary-foreground',
                                name: 'secondary-foreground',
                                tailwindClass: 'text-secondary-foreground',
                                value: semanticColors['secondary-foreground'][0],
                            },
                        ]}
                        usages={['Secondary background of the app']}
                    />

                    <ColorSwatch
                        name="Muted"
                        items={[
                            {
                                className: 'bg-muted',
                                name: 'muted',
                                tailwindClass: 'bg-muted',
                                value: semanticColors.muted[0],
                            },
                            {
                                className: 'text-muted-foreground',
                                name: 'muted-foreground',
                                tailwindClass: 'text-muted-foreground',
                                value: semanticColors['muted-foreground'][0],
                            },
                        ]}
                        usages={['Muted background of the app']}
                    />

                    <ColorSwatch
                        name="Accent"
                        items={[
                            {
                                className: 'bg-accent',
                                name: 'accent',
                                tailwindClass: 'bg-accent',
                                value: semanticColors.accent[0],
                            },
                            {
                                className: 'text-accent-foreground',
                                name: 'accent-foreground',
                                tailwindClass: 'text-accent-foreground',
                                value: semanticColors['accent-foreground'][0],
                            },
                        ]}
                        usages={['Accent (used for hover states, etc.)`']}
                    />

                    <div className="p-2 font-mono bg-muted text-muted-foreground">
                        muted/muted-foreground: {semanticColors.muted[0]}
                    </div>
                    <div className="p-2 font-mono bg-accent text-accent-foreground">
                        accent/accent-foreground: {semanticColors.accent[0]}
                    </div>
                    <div className="p-2 font-mono bg-destructive text-destructive-foreground">
                        destructive/destructive-foreground: {semanticColors.destructive[0]}
                    </div>
                    <div className="p-2 font-mono bg-success text-success-foreground">
                        success/success-foreground: {semanticColors.success[0]}
                    </div>
                    <div className="p-2 font-mono bg-warning text-warning-foreground">
                        warning/warning-foreground: {semanticColors.warning[0]}
                    </div>
                    <div className="p-2 font-mono bg-info text-info-foreground">
                        info/info-foreground: {semanticColors.info[0]}
                    </div>
                    <div className="p-2 font-mono bg-border text-foreground">
                        border/foreground: {semanticColors.border[0]}
                    </div>
                    <div className="p-2 font-mono bg-input text-foreground">
                        input/foreground: {semanticColors.input[0]}
                    </div>
                    <div className="p-2 font-mono bg-ring text-foreground">
                        ring/foreground: {semanticColors.ring[0]}
                    </div>
                </div>
            </div>
        )
    },
}
