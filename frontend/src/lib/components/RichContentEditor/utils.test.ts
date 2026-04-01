import { Editor } from '@tiptap/core'
import Document from '@tiptap/extension-document'
import Paragraph from '@tiptap/extension-paragraph'
import Text from '@tiptap/extension-text'

import { createEditor } from './utils'
import { JSONContent } from './types'

const ParagraphWithNotebookAttrs = Paragraph.extend({
    addAttributes() {
        return {
            ...this.parent?.(),
            nodeId: { default: null },
            query: { default: null },
        }
    },
})

const initialContent: JSONContent = {
    type: 'doc',
    content: [
        {
            type: 'paragraph',
            content: [{ type: 'text', text: 'Heading' }],
        },
        {
            type: 'paragraph',
            attrs: { nodeId: 'node-1', query: { foo: 'bar' } },
        },
        {
            type: 'paragraph',
            attrs: { nodeId: 'node-2', query: { count: 1 } },
        },
    ],
}

function createTestEditor(content: JSONContent = initialContent): Editor {
    return new Editor({
        extensions: [Document, ParagraphWithNotebookAttrs, Text],
        content,
    })
}

describe('createEditor.mergeContent', () => {
    it('updates matching nodes in place and keeps untouched nodes stable', async () => {
        const editor = createTestEditor()
        const richEditor = createEditor(editor)
        const originalDoc = editor.state.doc
        const firstNodeBefore = originalDoc.child(0)
        const nodeTwoBefore = originalDoc.child(2)

        richEditor.mergeContent({
            type: 'doc',
            content: [
                {
                    type: 'paragraph',
                    content: [{ type: 'text', text: 'Heading' }],
                },
                {
                    type: 'paragraph',
                    attrs: { nodeId: 'node-1', query: { foo: 'baz' } },
                },
                {
                    type: 'paragraph',
                    attrs: { nodeId: 'node-2', query: { count: 1 } },
                },
            ],
        })

        await Promise.resolve()

        expect(editor.state.doc.child(0)).toBe(firstNodeBefore)
        expect(editor.state.doc.child(2)).toBe(nodeTwoBefore)
        expect(editor.getJSON()).toEqual({
            type: 'doc',
            content: [
                {
                    type: 'paragraph',
                    content: [{ type: 'text', text: 'Heading' }],
                },
                {
                    type: 'paragraph',
                    attrs: { nodeId: 'node-1', query: { foo: 'baz' } },
                },
                {
                    type: 'paragraph',
                    attrs: { nodeId: 'node-2', query: { count: 1 } },
                },
            ],
        })

        editor.destroy()
    })

    it('inserts and deletes top-level nodes by nodeId', async () => {
        const editor = createTestEditor()
        const richEditor = createEditor(editor)

        richEditor.mergeContent({
            type: 'doc',
            content: [
                {
                    type: 'paragraph',
                    content: [{ type: 'text', text: 'Heading' }],
                },
                {
                    type: 'paragraph',
                    attrs: { nodeId: 'node-3', query: { inserted: true } },
                },
                {
                    type: 'paragraph',
                    attrs: { nodeId: 'node-2', query: { count: 2 } },
                },
            ],
        })

        await Promise.resolve()

        expect(editor.getJSON()).toEqual({
            type: 'doc',
            content: [
                {
                    type: 'paragraph',
                    content: [{ type: 'text', text: 'Heading' }],
                },
                {
                    type: 'paragraph',
                    attrs: { nodeId: 'node-3', query: { inserted: true } },
                },
                {
                    type: 'paragraph',
                    attrs: { nodeId: 'node-2', query: { count: 2 } },
                },
            ],
        })

        editor.destroy()
    })

    it('skips updating actively edited nodes', async () => {
        const editor = createTestEditor()
        const richEditor = createEditor(editor)

        richEditor.mergeContent(
            {
                type: 'doc',
                content: [
                    {
                        type: 'paragraph',
                        content: [{ type: 'text', text: 'Heading' }],
                    },
                    {
                        type: 'paragraph',
                        attrs: { nodeId: 'node-1', query: { foo: 'server-value' } },
                    },
                    {
                        type: 'paragraph',
                        attrs: { nodeId: 'node-2', query: { count: 2 } },
                    },
                ],
            },
            { skipNodeIds: { 'node-1': true } }
        )

        await Promise.resolve()

        expect(editor.getJSON()).toEqual({
            type: 'doc',
            content: [
                {
                    type: 'paragraph',
                    content: [{ type: 'text', text: 'Heading' }],
                },
                {
                    type: 'paragraph',
                    attrs: { nodeId: 'node-1', query: { foo: 'bar' } },
                },
                {
                    type: 'paragraph',
                    attrs: { nodeId: 'node-2', query: { count: 2 } },
                },
            ],
        })

        editor.destroy()
    })
})
