import { Editor, Node } from '@tiptap/core'
import Document from '@tiptap/extension-document'
import StarterKit from '@tiptap/starter-kit'

import { createEditor } from './utils'
import { JSONContent } from './types'

const NotebookParagraph = Node.create({
    name: 'paragraph',
    group: 'block',
    content: 'inline*',
    parseHTML() {
        return [{ tag: 'p' }]
    },
    renderHTML({ HTMLAttributes }) {
        return ['p', HTMLAttributes, 0]
    },
    addAttributes() {
        return {
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
        extensions: [Document, NotebookParagraph, StarterKit.configure({ document: false, paragraph: false })],
        content,
    })
}

function normalizeJson(content: JSONContent): JSONContent {
    return JSON.parse(JSON.stringify(content)) as JSONContent
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
        expect(normalizeJson(editor.getJSON() as JSONContent)).toEqual({
            type: 'doc',
            content: [
                {
                    type: 'paragraph',
                    attrs: { nodeId: null, query: null },
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

        expect(normalizeJson(editor.getJSON() as JSONContent)).toEqual({
            type: 'doc',
            content: [
                {
                    type: 'paragraph',
                    attrs: { nodeId: null, query: null },
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

        expect(normalizeJson(editor.getJSON() as JSONContent)).toEqual({
            type: 'doc',
            content: [
                {
                    type: 'paragraph',
                    attrs: { nodeId: null, query: null },
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
