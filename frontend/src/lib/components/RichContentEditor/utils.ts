import {
    EditorFocusPosition,
    EditorRange,
    JSONContent,
    MergeContentOptions,
    RichContentEditorType,
    RichContentNode,
    RichContentNodeType,
    TTEditor,
} from './types'
import { Node as PMNode } from '@tiptap/pm/model'

type MergeNode = {
    pmNode: PMNode
    nodeId: string | null
}

type EditorTransaction = TTEditor['state']['tr']

export function createEditor(editor: TTEditor): RichContentEditorType {
    return {
        isEmpty: () => editor.isEmpty,
        getJSON: () => editor.getJSON(),
        getEndPosition: () => editor.state.doc.content.size,
        getSelectedNode: () => editor.state.doc.nodeAt(editor.state.selection.$anchor.pos),
        getCurrentPosition: () => editor.state.selection.$anchor.pos,
        getAdjacentNodes: (pos: number) => getAdjacentNodes(editor, pos),
        setEditable: (editable: boolean) => queueMicrotask(() => editor.setEditable(editable, false)),
        setContent: (content: JSONContent) =>
            queueMicrotask(() => editor.commands.setContent(content, { emitUpdate: false })),
        mergeContent: (content: JSONContent, options?: MergeContentOptions) =>
            queueMicrotask(() => mergeContent(editor, content, options)),
        setSelection: (position: number) => editor.commands.setNodeSelection(position),
        setTextSelection: (position: number | EditorRange) =>
            queueMicrotask(() => editor.commands.setTextSelection(position)),
        focus: (position?: EditorFocusPosition) => queueMicrotask(() => editor.commands.focus(position)),
        clear: () => editor.commands.clearContent(),
        chain: () => editor.chain().focus(),
        destroy: () => editor.destroy(),
        getMarks: (type: string) => getMarks(editor, type),
        setMark: (id: string) => editor.commands.setMark('comment', { id }),
        isActive: (name: string, attributes?: {}) => editor.isActive(name, attributes),
        getMentions: () => getMentions(editor),
        deleteRange: (range: EditorRange) => editor.chain().focus().deleteRange(range),
        insertContent: (content: JSONContent) => editor.chain().insertContent(content).focus().run(),
        insertContentAt: (position: number, content: JSONContent) => {
            editor.chain().focus().insertContentAt(position, content).run()
            editor.commands.scrollIntoView()
        },
        insertContentAfterNode: (position: number, content: JSONContent) => {
            const endPosition = findEndPositionOfNode(editor, position)
            if (endPosition) {
                editor.chain().focus().insertContentAt(endPosition, content).run()
                editor.commands.scrollIntoView()
            }
        },
        pasteContent: (position: number, text: string) => {
            editor?.chain().focus().setTextSelection(position).run()
            editor?.view.pasteText(text)
        },
        findNode: (position: number) => findNode(editor, position),
        findNodePositionByAttrs: (attrs: Record<string, any>) => findNodePositionByAttrs(editor, attrs),
        nextNode: (position: number) => nextNode(editor, position),
        hasChildOfType: (node: RichContentNode, type: string) => !!firstChildOfType(node, type),
        scrollToSelection: () => {
            queueMicrotask(() => {
                const position = editor.state.selection.$anchor.pos
                const domEl = editor.view.nodeDOM(position) as HTMLElement
                domEl.scrollIntoView({ behavior: 'smooth', block: 'start', inline: 'nearest' })
            })
        },
        scrollToPosition(position) {
            queueMicrotask(() => {
                const domEl = editor.view.nodeDOM(position) as HTMLElement
                domEl.scrollIntoView({ behavior: 'smooth', block: 'start', inline: 'nearest' })
            })
        },
    }
}

export function hasChildOfType(node: RichContentNode, type: string, direct: boolean = true): boolean {
    const types: string[] = []
    node.descendants((child) => {
        types.push(child.type.name)
        return !direct
    })
    return types.includes(type)
}

export function firstChildOfType(node: RichContentNode, type: string, direct: boolean = true): RichContentNode | null {
    const children = getChildren(node, direct)
    return children.find((child) => child.type.name === type) || null
}

function findNodePositionByAttrs(editor: TTEditor, attrs: { [attr: string]: any }): number {
    return findPositionOfClosestNodeMatchingAttrs(editor, 0, attrs)
}

function findEndPositionOfNode(editor: TTEditor, position: number): number | null {
    const node = findNode(editor, position)
    return !node ? null : position + node.nodeSize
}

function findNode(editor: TTEditor, position: number): RichContentNode | null {
    return editor.state.doc.nodeAt(position)
}

function nextNode(editor: TTEditor, position: number): { node: RichContentNode; position: number } | null {
    const endPosition = findEndPositionOfNode(editor, position)
    if (!endPosition) {
        return null
    }
    const result = editor.state.doc.childAfter(endPosition)
    return result.node ? { node: result.node, position: result.offset } : null
}

function findPositionOfClosestNodeMatchingAttrs(editor: TTEditor, pos: number, attrs: { [attr: string]: any }): number {
    const matchingPositions: number[] = []
    const attrEntries = Object.entries(attrs)

    editor.state.doc.descendants((node, pos) => {
        if (attrEntries.every(([attr, value]) => node.attrs[attr] === value)) {
            matchingPositions.push(pos)
        }
    })

    return closest(matchingPositions, pos)
}

function closest(array: number[], num: number): number {
    return array.sort((a, b) => Math.abs(num - a) - Math.abs(num - b))[0]
}

function getChildren(node: RichContentNode, direct: boolean = true): RichContentNode[] {
    const children: RichContentNode[] = []
    node.descendants((child) => {
        children.push(child)
        return !direct
    })
    return children
}

function mergeContent(editor: TTEditor, content: JSONContent, options?: MergeContentOptions): void {
    const nextDoc = editor.schema.nodeFromJSON(normalizeDocumentContent(content))
    const workingNodes = getTopLevelNodes(editor.state.doc)
    const targetNodes = getTopLevelNodes(nextDoc)
    let tr = editor.state.tr
    let currentIndex = 0
    let targetIndex = 0

    while (targetIndex < targetNodes.length || currentIndex < workingNodes.length) {
        const currentNode = workingNodes[currentIndex]
        const targetNode = targetNodes[targetIndex]

        if (!currentNode && targetNode) {
            tr = insertNodeAtIndex(tr, workingNodes, currentIndex, targetNode)
            currentIndex += 1
            targetIndex += 1
            continue
        }

        if (currentNode && !targetNode) {
            if (shouldSkipNode(currentNode, options)) {
                currentIndex += 1
                continue
            }

            tr = deleteNodeAtIndex(tr, workingNodes, currentIndex)
            continue
        }

        if (!currentNode || !targetNode) {
            break
        }

        if (nodesMatch(currentNode, targetNode)) {
            if (!shouldSkipNode(currentNode, options) && !currentNode.pmNode.eq(targetNode.pmNode)) {
                tr = syncMatchedNodeAtIndex(tr, workingNodes, currentIndex, targetNode)
            }

            currentIndex += 1
            targetIndex += 1
            continue
        }

        const currentNodeAppearsLaterInTarget = findNodeIndexById(targetNodes, currentNode.nodeId, targetIndex + 1)
        const targetNodeAppearsLaterInCurrent = findNodeIndexById(workingNodes, targetNode.nodeId, currentIndex + 1)

        if (shouldSkipNode(currentNode, options)) {
            if (currentNodeAppearsLaterInTarget !== -1) {
                tr = insertNodeAtIndex(tr, workingNodes, currentIndex, targetNode)
                currentIndex += 1
                targetIndex += 1
                continue
            }

            currentIndex += 1
            continue
        }

        if (
            currentNodeAppearsLaterInTarget !== -1 &&
            (targetNodeAppearsLaterInCurrent === -1 || currentNodeAppearsLaterInTarget < targetNodeAppearsLaterInCurrent)
        ) {
            tr = insertNodeAtIndex(tr, workingNodes, currentIndex, targetNode)
            currentIndex += 1
            targetIndex += 1
            continue
        }

        if (targetNodeAppearsLaterInCurrent !== -1) {
            tr = deleteNodeAtIndex(tr, workingNodes, currentIndex)
            continue
        }

        tr = replaceNodeAtIndex(tr, workingNodes, currentIndex, targetNode)
        currentIndex += 1
        targetIndex += 1
    }

    if (tr.docChanged) {
        editor.view.dispatch(tr.setMeta('preventUpdate', true))
    }
}

function normalizeDocumentContent(content: JSONContent): JSONContent {
    const rawContent = content as JSONContent | JSONContent[]

    if (Array.isArray(rawContent)) {
        return { type: 'doc', content: rawContent }
    }

    if (rawContent.type === 'doc') {
        return rawContent
    }

    return { type: 'doc', content: [rawContent] }
}

function getTopLevelNodes(doc: PMNode): MergeNode[] {
    const nodes: MergeNode[] = []

    doc.forEach((node) => {
        nodes.push({
            pmNode: node,
            nodeId: getNodeId(node.attrs),
        })
    })

    return nodes
}

function getNodeId(attrs: Record<string, any> | undefined): string | null {
    return typeof attrs?.nodeId === 'string' && attrs.nodeId.length > 0 ? attrs.nodeId : null
}

function shouldSkipNode(node: MergeNode, options?: MergeContentOptions): boolean {
    return !!(node.nodeId && options?.skipNodeIds?.[node.nodeId])
}

function nodesMatch(currentNode: MergeNode, targetNode: MergeNode): boolean {
    if (currentNode.nodeId || targetNode.nodeId) {
        return currentNode.nodeId !== null && currentNode.nodeId === targetNode.nodeId
    }

    return currentNode.pmNode.type === targetNode.pmNode.type
}

function findNodeIndexById(nodes: MergeNode[], nodeId: string | null, startIndex: number): number {
    if (!nodeId) {
        return -1
    }

    for (let index = startIndex; index < nodes.length; index++) {
        if (nodes[index].nodeId === nodeId) {
            return index
        }
    }

    return -1
}

function getPositionAtIndex(nodes: MergeNode[], index: number): number {
    let position = 0

    for (let nodeIndex = 0; nodeIndex < index; nodeIndex++) {
        position += nodes[nodeIndex].pmNode.nodeSize
    }

    return position
}

function insertNodeAtIndex(tr: EditorTransaction, nodes: MergeNode[], index: number, node: MergeNode): EditorTransaction {
    tr.insert(getPositionAtIndex(nodes, index), node.pmNode)
    nodes.splice(index, 0, node)
    return tr
}

function deleteNodeAtIndex(tr: EditorTransaction, nodes: MergeNode[], index: number): EditorTransaction {
    const position = getPositionAtIndex(nodes, index)
    tr.delete(position, position + nodes[index].pmNode.nodeSize)
    nodes.splice(index, 1)
    return tr
}

function replaceNodeAtIndex(tr: EditorTransaction, nodes: MergeNode[], index: number, node: MergeNode): EditorTransaction {
    const position = getPositionAtIndex(nodes, index)
    tr.replaceWith(position, position + nodes[index].pmNode.nodeSize, node.pmNode)
    nodes[index] = node
    return tr
}

function syncMatchedNodeAtIndex(
    tr: EditorTransaction,
    nodes: MergeNode[],
    index: number,
    node: MergeNode
): EditorTransaction {
    const position = getPositionAtIndex(nodes, index)
    const currentNode = nodes[index]

    if (currentNode.pmNode.type === node.pmNode.type && currentNode.pmNode.content.eq(node.pmNode.content)) {
        tr.setNodeMarkup(position, node.pmNode.type, node.pmNode.attrs, node.pmNode.marks)
        nodes[index] = node
        return tr
    }

    return replaceNodeAtIndex(tr, nodes, index, node)
}

function getAdjacentNodes(
    editor: TTEditor,
    pos: number
): { previous: RichContentNode | null; next: RichContentNode | null } {
    const { doc } = editor.state
    const currentIndex = doc.resolve(pos).index(0)
    return { previous: doc.maybeChild(currentIndex - 1), next: doc.maybeChild(currentIndex + 1) }
}

function getMarks(editor: TTEditor, type: string): { id: string; pos: number }[] {
    const results: { id: string; pos: number }[] = []
    const doc = editor.state.doc

    doc.descendants((node, pos) => {
        const marks = node.marks.filter((mark) => mark.type.name === type)
        marks.forEach((mark) => results.push({ id: mark.attrs.id, pos }))
    })

    return results
}

function getMentions(editor: TTEditor): number[] {
    const mentions: number[] = []

    editor.state.doc.descendants((node) => {
        if (node.type.name === RichContentNodeType.Mention) {
            mentions.push(node.attrs.id)
        }
    })

    return mentions
}
