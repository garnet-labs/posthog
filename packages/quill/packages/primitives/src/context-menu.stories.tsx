import type { Meta, StoryObj } from '@storybook/react-vite'
import { Copy, MoreVertical, Pencil, TrashIcon } from 'lucide-react'

import { Button } from './button'
import {
    ContextMenu,
    ContextMenuContent,
    ContextMenuGroup,
    ContextMenuItem,
    ContextMenuSeparator,
    ContextMenuSub,
    ContextMenuSubContent,
    ContextMenuSubTrigger,
    ContextMenuTrigger,
} from './context-menu'

const meta = {
    title: 'Primitives/ContextMenu',
    component: ContextMenu,
    tags: ['autodocs'],
} satisfies Meta<typeof ContextMenu>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
    render: () => (
        <ContextMenu>
            <ContextMenuTrigger render={<Button variant="outline" size="sm" />}>Side-click me</ContextMenuTrigger>
            <ContextMenuContent>
                <ContextMenuGroup>
                    <ContextMenuItem>
                        <Copy />
                        Copy
                    </ContextMenuItem>
                    <ContextMenuItem>
                        <Pencil />
                        Rename
                    </ContextMenuItem>
                    <ContextMenuItem variant="destructive">
                        <TrashIcon />
                        Delete
                    </ContextMenuItem>
                </ContextMenuGroup>
                <ContextMenuSeparator />
                <ContextMenuSub>
                    <ContextMenuSubTrigger>
                        <MoreVertical />
                        More
                    </ContextMenuSubTrigger>
                    <ContextMenuSubContent>
                        <ContextMenuItem>
                            <Copy />
                            Copy
                        </ContextMenuItem>
                    </ContextMenuSubContent>
                </ContextMenuSub>
            </ContextMenuContent>
        </ContextMenu>
    ),
} satisfies Story
