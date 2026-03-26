import type { Meta, StoryObj } from '@storybook/react-vite'

import { Input } from './input'
import { Field, FieldDescription, FieldLabel } from './field'
import { SearchIcon } from 'lucide-react'
import { Button } from './button'
import { Textarea } from './textarea'

const meta = {
    title: 'Primitives/Fields',
    tags: ['autodocs'],
} satisfies Meta<typeof Field>

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

export const TextareaDefault: Story = {
    render: () => (
        <Field>
            <Textarea id="textarea-message" placeholder="Type your message here." />
        </Field>
    ),
} satisfies Story

export const TextareaWithLabel: Story = {
    render: () => (
        <Field>
            <FieldLabel htmlFor="textarea-message">Message</FieldLabel>
            <Textarea id="textarea-message" placeholder="Type your message here." />
        </Field>
    ),
} satisfies Story

export const TextareaWithDescription: Story = {
    render: () => (
        <Field>
            <FieldLabel htmlFor="textarea-message">Message</FieldLabel>
            <Textarea id="textarea-message" placeholder="Type your message here." />
            <FieldDescription>Enter your message below.</FieldDescription>
        </Field>
    ),
} satisfies Story

export const TextareaDisabled: Story = {
    render: () => (
        <Field data-disabled>
            <FieldLabel htmlFor="textarea-message">Message</FieldLabel>
            <Textarea id="textarea-message" placeholder="Type your message here." disabled />
        </Field>
    ),
} satisfies Story

export const TextareaInvalid: Story = {
    render: () => (
        <Field data-invalid>
            <FieldLabel htmlFor="textarea-invalid">Message</FieldLabel>
            <Textarea
                id="textarea-invalid"
                placeholder="Type your message here."
                aria-invalid
            />
            <FieldDescription>Please enter a valid message.</FieldDescription>
        </Field>
    ),
} satisfies Story