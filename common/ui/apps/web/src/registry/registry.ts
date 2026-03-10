import { lazy } from 'react'

// Raw source imports for code display
import AccordionBasicCode from '../examples/accordion/AccordionBasic.tsx?raw'
import BadgeBasicCode from '../examples/badge/BadgeBasic.tsx?raw'
import ButtonBasicCode from '../examples/button/ButtonBasic.tsx?raw'
import ButtonSizesCode from '../examples/button/ButtonSizes.tsx?raw'
import ButtonVariantsCode from '../examples/button/ButtonVariants.tsx?raw'
import CardBasicCode from '../examples/card/CardBasic.tsx?raw'
import CheckboxBasicCode from '../examples/checkbox/CheckboxBasic.tsx?raw'
import InputBasicCode from '../examples/input/InputBasic.tsx?raw'
import SeparatorBasicCode from '../examples/separator/SeparatorBasic.tsx?raw'
import SkeletonBasicCode from '../examples/skeleton/SkeletonBasic.tsx?raw'
import SliderBasicCode from '../examples/slider/SliderBasic.tsx?raw'
import SwitchBasicCode from '../examples/switch/SwitchBasic.tsx?raw'
import TabsBasicCode from '../examples/tabs/TabsBasic.tsx?raw'
import ToggleBasicCode from '../examples/toggle/ToggleBasic.tsx?raw'
import type { ComponentEntry } from './types'

export const registry: ComponentEntry[] = [
    {
        slug: 'accordion',
        name: 'Accordion',
        description: 'A set of collapsible panels with headings.',
        category: 'Display',
        anatomy: `<Accordion type="single" collapsible>
  <AccordionItem value="item-1">
    <AccordionTrigger>Title</AccordionTrigger>
    <AccordionContent>Content</AccordionContent>
  </AccordionItem>
</Accordion>`,
        props: [
            {
                name: 'type',
                type: '"single" | "multiple"',
                description: 'Whether one or multiple items can be open at the same time.',
            },
            {
                name: 'collapsible',
                type: 'boolean',
                default: 'false',
                description: 'When type is "single", allows closing all items.',
            },
            { name: 'defaultValue', type: 'string | string[]', description: 'The default open item(s).' },
        ],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/accordion/AccordionBasic')),
                code: AccordionBasicCode,
            },
        ],
    },
    {
        slug: 'badge',
        name: 'Badge',
        description: 'A small status indicator label.',
        category: 'Display',
        anatomy: `<Badge variant="default">Badge</Badge>`,
        props: [
            {
                name: 'variant',
                type: '"default" | "secondary" | "outline" | "destructive"',
                default: '"default"',
                description: 'Visual style variant.',
            },
        ],
        examples: [
            {
                name: 'Variants',
                component: lazy(() => import('../examples/badge/BadgeBasic')),
                code: BadgeBasicCode,
            },
        ],
    },
    {
        slug: 'button',
        name: 'Button',
        description: 'Trigger actions or events with configurable styles and sizes.',
        category: 'Inputs',
        anatomy: `<Button variant="default" size="default">Click me</Button>`,
        props: [
            {
                name: 'variant',
                type: '"default" | "secondary" | "outline" | "ghost" | "destructive" | "link"',
                default: '"default"',
                description: 'Visual style variant.',
            },
            {
                name: 'size',
                type: '"default" | "xs" | "sm" | "lg" | "icon" | "icon-xs" | "icon-sm" | "icon-lg"',
                default: '"default"',
                description: 'Button size.',
            },
            {
                name: 'asChild',
                type: 'boolean',
                default: 'false',
                description: 'Merge props onto a child element instead of rendering a <button>.',
            },
        ],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/button/ButtonBasic')),
                code: ButtonBasicCode,
            },
            {
                name: 'Variants',
                component: lazy(() => import('../examples/button/ButtonVariants')),
                code: ButtonVariantsCode,
            },
            {
                name: 'Sizes',
                component: lazy(() => import('../examples/button/ButtonSizes')),
                code: ButtonSizesCode,
            },
        ],
    },
    {
        slug: 'card',
        name: 'Card',
        description: 'A container for grouping related content and actions.',
        category: 'Display',
        anatomy: `<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Description</CardDescription>
  </CardHeader>
  <CardContent>Content</CardContent>
  <CardFooter>Footer</CardFooter>
</Card>`,
        props: [],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/card/CardBasic')),
                code: CardBasicCode,
            },
        ],
    },
    {
        slug: 'checkbox',
        name: 'Checkbox',
        description: 'A control that allows selecting one or more options.',
        category: 'Inputs',
        anatomy: `<Checkbox id="check" />
<Label htmlFor="check">Label</Label>`,
        props: [
            { name: 'checked', type: 'boolean', description: 'Controlled checked state.' },
            {
                name: 'onCheckedChange',
                type: '(checked: boolean) => void',
                description: 'Callback when checked state changes.',
            },
            { name: 'disabled', type: 'boolean', default: 'false', description: 'Whether the checkbox is disabled.' },
        ],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/checkbox/CheckboxBasic')),
                code: CheckboxBasicCode,
            },
        ],
    },
    {
        slug: 'input',
        name: 'Input',
        description: 'A text input field for collecting user data.',
        category: 'Inputs',
        anatomy: `<Input type="text" placeholder="Enter value" />`,
        props: [
            { name: 'type', type: 'string', default: '"text"', description: 'HTML input type.' },
            { name: 'placeholder', type: 'string', description: 'Placeholder text.' },
            { name: 'disabled', type: 'boolean', default: 'false', description: 'Whether the input is disabled.' },
        ],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/input/InputBasic')),
                code: InputBasicCode,
            },
        ],
    },
    {
        slug: 'separator',
        name: 'Separator',
        description: 'A visual divider between content sections.',
        category: 'Layout',
        anatomy: `<Separator orientation="horizontal" />`,
        props: [
            {
                name: 'orientation',
                type: '"horizontal" | "vertical"',
                default: '"horizontal"',
                description: 'Orientation of the separator.',
            },
        ],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/separator/SeparatorBasic')),
                code: SeparatorBasicCode,
            },
        ],
    },
    {
        slug: 'skeleton',
        name: 'Skeleton',
        description: 'A placeholder loading animation for content.',
        category: 'Display',
        anatomy: `<Skeleton className="h-4 w-[200px]" />`,
        props: [],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/skeleton/SkeletonBasic')),
                code: SkeletonBasicCode,
            },
        ],
    },
    {
        slug: 'slider',
        name: 'Slider',
        description: 'A range input for selecting numeric values.',
        category: 'Inputs',
        anatomy: `<Slider defaultValue={[50]} max={100} step={1} />`,
        props: [
            { name: 'defaultValue', type: 'number[]', description: 'Default slider value(s).' },
            { name: 'max', type: 'number', default: '100', description: 'Maximum value.' },
            { name: 'step', type: 'number', default: '1', description: 'Step increment.' },
        ],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/slider/SliderBasic')),
                code: SliderBasicCode,
            },
        ],
    },
    {
        slug: 'switch',
        name: 'Switch',
        description: 'A toggle control for binary on/off states.',
        category: 'Inputs',
        anatomy: `<Switch id="toggle" />
<Label htmlFor="toggle">Label</Label>`,
        props: [
            { name: 'checked', type: 'boolean', description: 'Controlled checked state.' },
            {
                name: 'onCheckedChange',
                type: '(checked: boolean) => void',
                description: 'Callback when state changes.',
            },
        ],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/switch/SwitchBasic')),
                code: SwitchBasicCode,
            },
        ],
    },
    {
        slug: 'tabs',
        name: 'Tabs',
        description: 'Organize content into switchable panels.',
        category: 'Display',
        anatomy: `<Tabs defaultValue="tab1">
  <TabsList>
    <TabsTrigger value="tab1">Tab 1</TabsTrigger>
    <TabsTrigger value="tab2">Tab 2</TabsTrigger>
  </TabsList>
  <TabsContent value="tab1">Content 1</TabsContent>
  <TabsContent value="tab2">Content 2</TabsContent>
</Tabs>`,
        props: [
            { name: 'defaultValue', type: 'string', description: 'Default active tab.' },
            { name: 'value', type: 'string', description: 'Controlled active tab.' },
            { name: 'onValueChange', type: '(value: string) => void', description: 'Callback when tab changes.' },
        ],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/tabs/TabsBasic')),
                code: TabsBasicCode,
            },
        ],
    },
    {
        slug: 'toggle',
        name: 'Toggle',
        description: 'A button that can be toggled on or off.',
        category: 'Inputs',
        anatomy: `<Toggle aria-label="Toggle">Label</Toggle>`,
        props: [
            {
                name: 'variant',
                type: '"default" | "outline"',
                default: '"default"',
                description: 'Visual style variant.',
            },
            { name: 'size', type: '"default" | "sm" | "lg"', default: '"default"', description: 'Toggle size.' },
            { name: 'pressed', type: 'boolean', description: 'Controlled pressed state.' },
        ],
        examples: [
            {
                name: 'Basic',
                component: lazy(() => import('../examples/toggle/ToggleBasic')),
                code: ToggleBasicCode,
            },
        ],
    },
]

export interface RegistryCategory {
    name: string
    components: ComponentEntry[]
}

export function getRegistryByCategory(): RegistryCategory[] {
    const categoryMap = new Map<string, ComponentEntry[]>()
    for (const entry of registry) {
        const list = categoryMap.get(entry.category) ?? []
        list.push(entry)
        categoryMap.set(entry.category, list)
    }
    return Array.from(categoryMap, ([name, components]) => ({ name, components }))
}
