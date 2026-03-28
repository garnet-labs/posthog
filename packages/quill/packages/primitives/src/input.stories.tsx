import type { Meta, StoryObj } from '@storybook/react-vite'

import { Field, FieldDescription, FieldLabel } from './field'
import { Input } from './input'

const meta = {
    title: 'Primitives/Input',
    tags: ['autodocs'],
} satisfies Meta<typeof Input>

export default meta
type Story = StoryObj<typeof meta>


export const InputDefault: Story = {
    render: () => (
        <Field>
            <Input placeholder="Enter your text" id="text" />
        </Field>
    ),
} satisfies Story

export const InputWithLabel: Story = {
    render: () => (
        <Field>
            <FieldLabel htmlFor="text">Text</FieldLabel>
            <Input placeholder="Enter your text" id="text" />
        </Field>
    ),
} satisfies Story

export const InputWithDescription: Story = {
    render: () => (
        <Field>
            <FieldLabel htmlFor="username">Username</FieldLabel>
            <Input placeholder="Enter your username" id="username" />
            <FieldDescription>Choose a unique username for your account.</FieldDescription>
        </Field>
    ),
} satisfies Story

export const InputPassword: Story = {
    render: () => (
        <Field>
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <Input placeholder="Enter your password" type="password" id="password" />
        </Field>
    ),
} satisfies Story

export const InputDisabled: Story = {
    render: () => (
        <Field data-disabled>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input placeholder="Enter your email" id="email" disabled />
        </Field>
    ),
} satisfies Story

export const InputInvalid: Story = {
    render: () => (
        <Field data-invalid>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input placeholder="Enter your email" id="email" aria-invalid />
        </Field>
    ),
} satisfies Story