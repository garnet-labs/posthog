import {
    DndContext,
    DragEndEvent,
    DragOverlay,
    DragStartEvent,
    MouseSensor,
    TouchSensor,
    pointerWithin,
    useSensor,
    useSensors,
    useDroppable,
    useDndMonitor,
} from '@dnd-kit/core'
import { SortableContext, useSortable, verticalListSortingStrategy, arrayMove } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useActions, useValues } from 'kea'
import { Form } from 'kea-forms'
import React, { useCallback, useMemo, useState } from 'react'

import { IconPlusSmall, IconTrash } from '@posthog/icons'
import {
    LemonButton,
    LemonDivider,
    LemonInput,
    LemonModal,
    LemonSelect,
    LemonSwitch,
    LemonTag,
} from '@posthog/lemon-ui'

import { getColorVar } from 'lib/colors'
import { AppMetricsFilters } from 'lib/components/AppMetrics/AppMetricsFilters'
import { appMetricsLogic } from 'lib/components/AppMetrics/appMetricsLogic'
import { AppMetricSummary } from 'lib/components/AppMetrics/AppMetricSummary'
import { IconDragHandle } from 'lib/lemon-ui/icons'
import { lemonToast } from 'lib/lemon-ui/LemonToast/LemonToast'
import { SceneExport } from 'scenes/sceneTypes'

import { SceneContent } from '~/layout/scenes/components/SceneContent'
import { SceneTitleSection } from '~/layout/scenes/components/SceneTitleSection'

import {
    eventFilterLogic,
    EVENT_FILTER_MAX_CONDITIONS,
    EVENT_FILTER_MAX_DEPTH,
    FilterNode,
    TestCase,
} from './eventFilterLogic'

export const scene: SceneExport = {
    component: EventFilterScene,
    logic: eventFilterLogic,
}

const FIELD_OPTIONS = [
    { value: 'event_name', label: 'Event name' },
    { value: 'distinct_id', label: 'Distinct ID' },
]

const OPERATOR_OPTIONS = [
    { value: 'exact', label: 'equals' },
    { value: 'contains', label: 'contains' },
]

// --- Stable node IDs ---
// Each node gets a `_nid` property. We stamp them when first seen and preserve
// them across tree mutations. This means DnD IDs don't change when indices shift.

let nidCounter = 0
function nextNid(): string {
    return `n${nidCounter++}`
}

type AnyNode = FilterNode & { _nid?: string }

/** Ensure every node in the tree has a stable `_nid`. Mutates in place. */
function stampNids(node: AnyNode): void {
    if (!node._nid) {
        node._nid = nextNid()
    }
    if (node.type === 'and' || node.type === 'or') {
        for (const child of node.children) {
            stampNids(child as AnyNode)
        }
    } else if (node.type === 'not') {
        stampNids(node.child as AnyNode)
    }
}

/** Get the _nid of a node */
function nid(node: FilterNode): string {
    return (node as AnyNode)._nid ?? ''
}

/** Build a map from _nid → tree path */
type NidIndex = Map<string, (string | number)[]>

function buildNidIndex(node: FilterNode, path: (string | number)[] = []): NidIndex {
    const index: NidIndex = new Map()
    const id = nid(node)
    if (id) {
        index.set(id, path)
    }
    if (node.type === 'and' || node.type === 'or') {
        for (let i = 0; i < node.children.length; i++) {
            const childIndex = buildNidIndex(node.children[i], [...path, 'children', i])
            for (const [k, v] of childIndex) {
                index.set(k, v)
            }
        }
    } else if (node.type === 'not') {
        const childIndex = buildNidIndex(node.child, [...path, 'child'])
        for (const [k, v] of childIndex) {
            index.set(k, v)
        }
    }
    return index
}

function getNodeAtPath(tree: FilterNode, path: (string | number)[]): any {
    let current: any = tree
    for (const key of path) {
        if (current == null) {
            return undefined
        }
        current = current[key]
    }
    return current
}

function splitParentChild(path: (string | number)[]): { parentPath: (string | number)[]; childIndex: number } | null {
    if (path.length < 2) {
        return null
    }
    const childIndex = path[path.length - 1]
    if (typeof childIndex !== 'number') {
        return null
    }
    return { parentPath: path.slice(0, -2), childIndex }
}

function isAncestorPath(a: (string | number)[], b: (string | number)[]): boolean {
    if (a.length >= b.length) {
        return false
    }
    return a.every((seg, i) => String(seg) === String(b[i]))
}

// --- Components ---

function SortableItem({ id, children }: { id: string; children: React.ReactNode }): JSX.Element {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.3 : 1,
    }
    return (
        <div ref={setNodeRef} style={style} className="flex items-start gap-1">
            <div className="mt-2 cursor-grab text-muted hover:text-default shrink-0" {...attributes} {...listeners}>
                <IconDragHandle />
            </div>
            <div className="flex-1 min-w-0">{children}</div>
        </div>
    )
}

function ConditionEditor({
    node,
    path,
    onDelete,
    showValidation,
}: {
    node: FilterNode & { type: 'condition' }
    path: (string | number)[]
    onDelete?: () => void
    showValidation?: boolean
}): JSX.Element {
    const { updateTreeNode } = useActions(eventFilterLogic)
    const isEmpty = showValidation && (!node.value || node.value.trim() === '')
    return (
        <div className="flex items-center gap-2 py-1">
            <LemonSelect
                size="small"
                options={FIELD_OPTIONS}
                value={node.field}
                onChange={(value) => updateTreeNode(path, { ...node, field: value as typeof node.field })}
            />
            <LemonSelect
                size="small"
                options={OPERATOR_OPTIONS}
                value={node.operator}
                onChange={(value) => updateTreeNode(path, { ...node, operator: value as typeof node.operator })}
            />
            <LemonInput
                size="small"
                value={node.value}
                onChange={(value) => updateTreeNode(path, { ...node, value })}
                placeholder="Value..."
                className="flex-1"
                status={isEmpty ? 'danger' : undefined}
            />
            {onDelete && (
                <LemonButton icon={<IconTrash />} size="xsmall" status="danger" onClick={onDelete} tooltip="Remove" />
            )}
        </div>
    )
}

function GroupEditor({
    node,
    path,
    depth,
    onDelete,
    showValidation,
}: {
    node: FilterNode & { type: 'and' | 'or' }
    path: (string | number)[]
    depth: number
    onDelete?: () => void
    showValidation?: boolean
}): JSX.Element {
    const { updateTreeNode, removeChild, wrapInNot, addChild } = useActions(eventFilterLogic)

    const droppableId = `drop:${nid(node)}`
    const { setNodeRef, isOver } = useDroppable({ id: droppableId })
    const borderColor = node.type === 'and' ? 'bg-[#2563EB]' : 'bg-[#F59E0B]'

    const childNids = node.children.map((child) => nid(child))

    // Track whether the drag is over this group or any of its direct children
    const [isOverGroup, setIsOverGroup] = useState(false)
    useDndMonitor({
        onDragOver(event) {
            if (!event.over) {
                setIsOverGroup(false)
                return
            }
            const overId = event.over.id as string
            // Check: over the group droppable itself, or over a direct child
            const isOverSelf = overId === droppableId
            const isOverChild = childNids.includes(overId)
            setIsOverGroup(isOverSelf || isOverChild)
        },
        onDragEnd() {
            setIsOverGroup(false)
        },
        onDragCancel() {
            setIsOverGroup(false)
        },
    })

    const shouldHighlight = isOver || isOverGroup

    return (
        <div ref={setNodeRef} className={`flex gap-0 ${shouldHighlight ? 'bg-fill-highlight rounded' : ''}`}>
            <div className={`w-0.5 shrink-0 rounded ${borderColor}`} />
            <div className="flex-1 min-w-0 py-1 pl-2 space-y-1">
                <div className="flex items-center gap-2">
                    <LemonSelect
                        size="xsmall"
                        options={[
                            { value: 'and', label: 'AND' },
                            { value: 'or', label: 'OR' },
                        ]}
                        value={node.type}
                        onChange={(value) =>
                            updateTreeNode(path, { type: value as 'and' | 'or', children: node.children })
                        }
                    />
                    <LemonButton size="xsmall" type="secondary" onClick={() => wrapInNot(path)}>
                        Negate
                    </LemonButton>
                    {onDelete && (
                        <LemonButton
                            icon={<IconTrash />}
                            size="xsmall"
                            status="danger"
                            onClick={onDelete}
                            tooltip="Remove"
                        />
                    )}
                </div>

                <SortableContext items={childNids} strategy={verticalListSortingStrategy}>
                    {node.children.map((child, i) => {
                        const childPath = [...path, 'children', i]
                        const childId = nid(child)
                        return (
                            <SortableItem key={childId} id={childId}>
                                <NodeEditor
                                    node={child}
                                    path={childPath}
                                    depth={depth + 1}
                                    onDelete={() => removeChild(path, i)}
                                    showValidation={showValidation}
                                />
                            </SortableItem>
                        )
                    })}
                </SortableContext>

                <div className="flex gap-2">
                    <LemonButton size="xsmall" type="secondary" icon={<IconPlusSmall />} onClick={() => addChild(path)}>
                        Add condition
                    </LemonButton>
                    <LemonButton
                        size="xsmall"
                        type="secondary"
                        icon={<IconPlusSmall />}
                        onClick={() => {
                            const newGroup: FilterNode = {
                                type: 'and',
                                children: [{ type: 'condition', field: 'event_name', operator: 'exact', value: '' }],
                            }
                            updateTreeNode(path, { ...node, children: [...node.children, newGroup] })
                        }}
                    >
                        Add group
                    </LemonButton>
                </div>
            </div>
        </div>
    )
}

function NodeEditor({
    node,
    path,
    depth,
    onDelete,
    showValidation,
}: {
    node: FilterNode
    path: (string | number)[]
    depth: number
    onDelete?: () => void
    showValidation?: boolean
}): JSX.Element {
    const { unwrapNot } = useActions(eventFilterLogic)

    if (node.type === 'condition') {
        return <ConditionEditor node={node} path={path} onDelete={onDelete} showValidation={showValidation} />
    }
    if (node.type === 'not') {
        return (
            <div className="border-l-2 border-danger pl-3 py-1 space-y-1">
                <div className="flex items-center gap-2">
                    <span className="text-danger font-semibold text-xs">NOT</span>
                    <LemonButton size="xsmall" status="danger" onClick={() => unwrapNot(path)}>
                        Remove NOT
                    </LemonButton>
                    {onDelete && (
                        <LemonButton
                            icon={<IconTrash />}
                            size="xsmall"
                            status="danger"
                            onClick={onDelete}
                            tooltip="Remove"
                        />
                    )}
                </div>
                <NodeEditor
                    node={node.child}
                    path={[...path, 'child']}
                    depth={depth + 1}
                    showValidation={showValidation}
                />
            </div>
        )
    }
    return <GroupEditor node={node} path={path} depth={depth} onDelete={onDelete} showValidation={showValidation} />
}

// --- Expression display ---

function isTreeEmpty(node: FilterNode): boolean {
    if (!node?.type) {
        return true
    }
    if (node.type === 'condition') {
        return false
    }
    if (node.type === 'not') {
        return isTreeEmpty(node.child)
    }
    return node.children.length === 0
}

function filterTreeToExpression(node: FilterNode, indent: number = 0): string {
    const pad = '  '.repeat(indent)
    switch (node.type) {
        case 'condition': {
            const op = node.operator === 'exact' ? '=' : '~'
            return `${pad}${node.field} ${op} "${node.value}"`
        }
        case 'not': {
            const inner = filterTreeToExpression(node.child, indent + 1)
            const isSimple = node.child.type === 'condition'
            if (isSimple) {
                return `${pad}NOT (${inner.trim()})`
            }
            return `${pad}NOT (\n${inner}\n${pad})`
        }
        case 'and':
        case 'or': {
            if (node.children.length === 0) {
                return `${pad}(empty)`
            }
            if (node.children.length === 1) {
                return filterTreeToExpression(node.children[0], indent)
            }
            const joiner = node.type === 'and' ? 'AND' : 'OR'
            const parts = node.children.map((child) => {
                const needsParens = (child.type === 'and' || child.type === 'or') && child.type !== node.type
                if (needsParens) {
                    const innerParts = child.children.map((c) => filterTreeToExpression(c, indent + 1))
                    const innerJoiner = child.type === 'and' ? 'AND' : 'OR'
                    const inner = innerParts.join(`\n${pad}  ${innerJoiner}\n`)
                    return `${pad}(\n${inner}\n${pad})`
                }
                return filterTreeToExpression(child, indent)
            })
            return parts.join(`\n${pad}${joiner}\n`)
        }
    }
}

const EVENT_FILTER_METRIC_KEYS = ['dropped'] as const

const EVENT_FILTER_METRICS_INFO: Record<string, { name: string; description: string; color: string }> = {
    dropped: {
        name: 'Events dropped by filters',
        description: 'Total number of events dropped by this filter',
        color: getColorVar('warning'),
    },
}

function EventFilterMetrics({ filterId }: { filterId: string | null }): JSX.Element | null {
    const logicKey = `event-filter-metrics-${filterId ?? 'none'}`

    const logic = filterId
        ? appMetricsLogic({
              logicKey,
              loadOnMount: true,
              loadOnChanges: true,
              forceParams: {
                  appSource: 'event_filter',
                  appSourceId: filterId,
                  metricName: [...EVENT_FILTER_METRIC_KEYS],
                  breakdownBy: 'metric_name',
              },
          })
        : null

    const { appMetricsTrendsLoading, getSingleTrendSeries } = useValues(logic ?? appMetricsLogic({ logicKey: 'noop' }))

    if (!filterId) {
        return null
    }

    return (
        <div className="space-y-2">
            <div className="flex items-center justify-between">
                <label className="font-semibold">Metrics</label>
                <AppMetricsFilters logicKey={logicKey} />
            </div>
            <div className="flex flex-row gap-2 flex-wrap">
                {EVENT_FILTER_METRIC_KEYS.map((key) => (
                    <AppMetricSummary
                        key={key}
                        name={EVENT_FILTER_METRICS_INFO[key].name}
                        description={EVENT_FILTER_METRICS_INFO[key].description}
                        loading={appMetricsTrendsLoading}
                        timeSeries={getSingleTrendSeries(key)}
                        previousPeriodTimeSeries={getSingleTrendSeries(key, true)}
                        color={EVENT_FILTER_METRICS_INFO[key].color}
                        colorIfZero={getColorVar('muted')}
                    />
                ))}
            </div>
            <p className="text-muted text-xs">
                These counts are approximate. The actual number of dropped events may differ by a small percentage.
            </p>
        </div>
    )
}

function nodeSummary(node: FilterNode): string {
    if (node.type === 'condition') {
        return `${node.field} ${node.operator} "${node.value}"`
    }
    if (node.type === 'not') {
        return 'NOT (...)'
    }
    return `${node.type.toUpperCase()} group (${node.children.length} items)`
}

// --- Main scene ---

export function EventFilterScene(): JSX.Element {
    const { filterForm, isFilterFormSubmitting, testResults, allTestsPass, filterFormErrors, showFilterFormErrors } =
        useValues(eventFilterLogic)
    const { setFilterFormValue, submitFilterForm, updateTreeNode, addTestCase, removeTestCase, updateTestCase } =
        useActions(eventFilterLogic)
    const [activeId, setActiveId] = useState<string | null>(null)
    const [showExpression, setShowExpression] = useState(false)

    // Stamp stable IDs on tree nodes (mutates in place, idempotent)
    stampNids(filterForm.filter_tree as AnyNode)

    // Build nid → path index on every render
    const nidIndex = useMemo(() => buildNidIndex(filterForm.filter_tree), [filterForm.filter_tree])

    const sensors = useSensors(
        useSensor(MouseSensor, { activationConstraint: { distance: 8 } }),
        useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } })
    )

    const handleDragStart = useCallback((event: DragStartEvent) => {
        setActiveId(event.active.id as string)
    }, [])

    const handleDragEnd = useCallback(
        (event: DragEndEvent) => {
            setActiveId(null)
            const { active, over } = event
            if (!over || active.id === over.id) {
                return
            }

            const activeNid = active.id as string
            const overIdStr = over.id as string
            const tree = filterForm.filter_tree
            const idx = buildNidIndex(tree)

            const activePath = idx.get(activeNid)
            if (!activePath) {
                return
            }
            const activeParent = splitParentChild(activePath)
            if (!activeParent) {
                return
            }

            // Determine target
            let targetGroupPath: (string | number)[]
            let insertIndex: number

            if (overIdStr.startsWith('drop:')) {
                // Dropped on a group droppable — append at end
                const groupNid = overIdStr.slice(5)
                const groupPath = idx.get(groupNid)
                if (!groupPath) {
                    return
                }
                targetGroupPath = groupPath
                const targetNode = groupPath.length === 0 ? tree : getNodeAtPath(tree, groupPath)
                if (!targetNode || (targetNode.type !== 'and' && targetNode.type !== 'or')) {
                    return
                }
                insertIndex = targetNode.children.length
            } else {
                // Dropped on a sortable item — insert at its position
                const overPath = idx.get(overIdStr)
                if (!overPath) {
                    return
                }
                const overParent = splitParentChild(overPath)
                if (!overParent) {
                    return
                }
                targetGroupPath = overParent.parentPath
                insertIndex = overParent.childIndex
            }

            // Prevent dropping into own descendant
            if (isAncestorPath(activePath, targetGroupPath)) {
                return
            }

            const sameGroup = activeParent.parentPath.join('.') === targetGroupPath.join('.')

            if (sameGroup) {
                // Reorder within same group
                const parentNode =
                    activeParent.parentPath.length === 0 ? tree : getNodeAtPath(tree, activeParent.parentPath)
                if (!parentNode || (parentNode.type !== 'and' && parentNode.type !== 'or')) {
                    return
                }
                const newChildren = arrayMove([...parentNode.children], activeParent.childIndex, insertIndex)
                updateTreeNode(activeParent.parentPath, { ...parentNode, children: newChildren })
            } else {
                // Move between groups
                const srcParent =
                    activeParent.parentPath.length === 0 ? tree : getNodeAtPath(tree, activeParent.parentPath)
                if (!srcParent || (srcParent.type !== 'and' && srcParent.type !== 'or')) {
                    return
                }

                const movedNode = srcParent.children[activeParent.childIndex]
                const newTree = JSON.parse(JSON.stringify(tree))

                // Remove from source first
                const newSrc =
                    activeParent.parentPath.length === 0 ? newTree : getNodeAtPath(newTree, activeParent.parentPath)
                if (newSrc && (newSrc.type === 'and' || newSrc.type === 'or')) {
                    newSrc.children.splice(activeParent.childIndex, 1)
                }

                // Recompute target path after removal (indices may have shifted)
                stampNids(newTree as AnyNode)
                const newIdx = buildNidIndex(newTree)
                let destGroupPath: (string | number)[]
                let destIndex: number

                if (overIdStr.startsWith('drop:')) {
                    const groupNid2 = overIdStr.slice(5)
                    destGroupPath = newIdx.get(groupNid2) ?? targetGroupPath
                    const destNode = destGroupPath.length === 0 ? newTree : getNodeAtPath(newTree, destGroupPath)
                    destIndex = destNode?.children?.length ?? 0
                } else {
                    const overPath2 = newIdx.get(overIdStr)
                    if (!overPath2) {
                        return
                    }
                    const overParent2 = splitParentChild(overPath2)
                    if (!overParent2) {
                        return
                    }
                    destGroupPath = overParent2.parentPath
                    destIndex = overParent2.childIndex
                }

                const newDst = destGroupPath.length === 0 ? newTree : getNodeAtPath(newTree, destGroupPath)
                if (newDst && (newDst.type === 'and' || newDst.type === 'or')) {
                    newDst.children.splice(destIndex, 0, JSON.parse(JSON.stringify(movedNode)))
                }

                setFilterFormValue('filter_tree', newTree)
            }
        },
        [filterForm.filter_tree, updateTreeNode, setFilterFormValue]
    )

    const activeNode = activeId ? getNodeAtPath(filterForm.filter_tree, nidIndex.get(activeId) ?? []) : null

    return (
        <SceneContent>
            <SceneTitleSection
                name="Event filters"
                description="Drop events at ingestion time based on event name or distinct ID."
                resourceType={{ type: 'data_pipeline' }}
            />
            <Form logic={eventFilterLogic} formKey="filterForm" enableFormOnSubmit>
                <div className="space-y-4">
                    <div className="border rounded p-3 text-sm">
                        <p className="mb-1">
                            Event filters are the most efficient way to drop unwanted events. They are evaluated early
                            in the ingestion pipeline, before transformations run.
                        </p>
                        <p className="mb-0">
                            Events that pass these filters will still go through any active{' '}
                            <strong>transformations</strong>, which can also drop or modify events. Use event filters
                            for simple drop rules based on event name or distinct ID, and only use transformations when
                            you need more complex logic.
                        </p>
                    </div>

                    <div
                        className={`border rounded p-3 flex items-center justify-between ${
                            filterForm.enabled ? 'border-success' : ''
                        }`}
                    >
                        <div>
                            <div className="font-semibold">
                                {filterForm.enabled ? 'Filter is active' : 'Filter is disabled'}
                            </div>
                            <div className="text-muted text-sm">
                                {filterForm.enabled
                                    ? 'Matching events are being dropped from ingestion.'
                                    : 'No events are being filtered. Enable to start dropping matching events.'}
                            </div>
                            {filterForm.enabled && !allTestsPass && filterForm.test_cases.length > 0 && (
                                <div className="text-danger text-xs mt-1">
                                    Tests failing — will be saved as disabled
                                </div>
                            )}
                        </div>
                        <LemonSwitch
                            checked={filterForm.enabled}
                            bordered
                            onChange={(value) => {
                                if (value && !allTestsPass && filterForm.test_cases.length > 0) {
                                    lemonToast.error('Cannot enable filter while test cases are failing')
                                    return
                                }
                                setFilterFormValue('enabled', value)
                            }}
                        />
                    </div>

                    <EventFilterMetrics filterId={filterForm.id} />

                    <div className="space-y-2">
                        <div className="flex items-start justify-between">
                            <div>
                                <label className="font-semibold">Drop events matching</label>
                                <p className="text-muted text-sm mb-0">
                                    Build a filter expression. Drag conditions and groups to reorder or move between
                                    groups. Maximum {EVENT_FILTER_MAX_CONDITIONS} conditions and{' '}
                                    {EVENT_FILTER_MAX_DEPTH} levels of nesting. Empty groups are removed automatically
                                    on save.
                                </p>
                            </div>
                            <LemonButton size="small" type="secondary" onClick={() => setShowExpression(true)}>
                                Show expression
                            </LemonButton>
                        </div>
                        <DndContext
                            sensors={sensors}
                            collisionDetection={pointerWithin}
                            onDragStart={handleDragStart}
                            onDragEnd={handleDragEnd}
                        >
                            <div className="border rounded p-3">
                                <NodeEditor
                                    node={filterForm.filter_tree}
                                    path={[]}
                                    depth={0}
                                    showValidation={showFilterFormErrors}
                                />
                            </div>
                            {showFilterFormErrors && filterFormErrors.filter_tree && (
                                <div className="text-danger text-sm mt-1">{filterFormErrors.filter_tree}</div>
                            )}
                            <DragOverlay>
                                {activeNode ? (
                                    <div className="bg-bg-light border rounded px-3 py-1 shadow-md text-sm">
                                        {nodeSummary(activeNode as FilterNode)}
                                    </div>
                                ) : null}
                            </DragOverlay>
                        </DndContext>
                        <LemonModal
                            isOpen={showExpression}
                            onClose={() => setShowExpression(false)}
                            title="Filter expression"
                            description="Events matching this expression will be dropped."
                        >
                            <pre className="font-mono text-sm whitespace-pre-wrap p-3 border rounded bg-bg-light overflow-auto max-h-96">
                                {isTreeEmpty(filterForm.filter_tree)
                                    ? '(no conditions configured)'
                                    : `DROP WHERE\n  ${filterTreeToExpression(filterForm.filter_tree, 1).trim()}`}
                            </pre>
                        </LemonModal>
                    </div>

                    <LemonDivider />

                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <label className="font-semibold">Test cases</label>
                            {filterForm.test_cases.length > 0 && (
                                <LemonTag type={allTestsPass ? 'success' : 'danger'}>
                                    {allTestsPass
                                        ? `All ${filterForm.test_cases.length} tests pass`
                                        : `${testResults.filter((r) => !r.pass).length} of ${filterForm.test_cases.length} failing`}
                                </LemonTag>
                            )}
                        </div>
                        <p className="text-muted text-sm">
                            Add test events to verify your filter. Each test specifies whether the event should be
                            dropped or ingested. The filter cannot be enabled until all tests pass.
                        </p>

                        {filterForm.test_cases.length > 0 && (
                            <div className="space-y-2">
                                {filterForm.test_cases.map((tc: TestCase, i: number) => {
                                    const result = testResults[i]
                                    return (
                                        <div
                                            key={i}
                                            className={`border rounded font-mono text-sm ${
                                                result && !result.pass ? 'border-danger' : ''
                                            }`}
                                        >
                                            <div className="flex items-center justify-between px-3 pt-2">
                                                <div className="flex items-center gap-2">
                                                    <LemonSelect
                                                        size="xsmall"
                                                        options={[
                                                            { value: 'drop', label: 'Should drop' },
                                                            { value: 'ingest', label: 'Should ingest' },
                                                        ]}
                                                        value={tc.expected_result}
                                                        onChange={(value) =>
                                                            updateTestCase(i, {
                                                                expected_result: value as 'drop' | 'ingest',
                                                            })
                                                        }
                                                    />
                                                    {result && (
                                                        <LemonTag type={result.pass ? 'success' : 'danger'}>
                                                            {result.pass ? 'Pass' : `Fail (would ${result.actual})`}
                                                        </LemonTag>
                                                    )}
                                                </div>
                                                <LemonButton
                                                    icon={<IconTrash />}
                                                    size="xsmall"
                                                    status="danger"
                                                    onClick={() => removeTestCase(i)}
                                                />
                                            </div>
                                            <div className="px-3 pb-2 pt-1">
                                                <span className="text-muted">{'{'}</span>
                                                <div className="pl-4 space-y-1">
                                                    <div className="flex items-center gap-1">
                                                        <span className="text-primary">"event"</span>
                                                        <span className="text-muted">:</span>
                                                        <LemonInput
                                                            size="small"
                                                            value={tc.event_name}
                                                            onChange={(value) =>
                                                                updateTestCase(i, { event_name: value })
                                                            }
                                                            placeholder="$pageview"
                                                            className="flex-1 font-mono"
                                                        />
                                                    </div>
                                                    <div className="flex items-center gap-1">
                                                        <span className="text-primary">"distinct_id"</span>
                                                        <span className="text-muted">:</span>
                                                        <LemonInput
                                                            size="small"
                                                            value={tc.distinct_id}
                                                            onChange={(value) =>
                                                                updateTestCase(i, { distinct_id: value })
                                                            }
                                                            placeholder="user-123"
                                                            className="flex-1 font-mono"
                                                        />
                                                    </div>
                                                </div>
                                                <span className="text-muted">{'}'}</span>
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        )}

                        <LemonButton
                            size="small"
                            type="secondary"
                            icon={<IconPlusSmall />}
                            onClick={() => addTestCase()}
                        >
                            Add test case
                        </LemonButton>
                    </div>

                    <LemonDivider />

                    {!allTestsPass && filterForm.enabled && (
                        <div className="text-danger text-sm">
                            Some test cases are failing. The filter cannot be enabled until all tests pass. You can save
                            with tests failing, but the filter will be saved as disabled.
                        </div>
                    )}

                    <div className="flex gap-2">
                        <LemonButton
                            type="primary"
                            onClick={() => {
                                if (filterForm.enabled && !allTestsPass) {
                                    setFilterFormValue('enabled', false)
                                }
                                submitFilterForm()
                            }}
                            loading={isFilterFormSubmitting}
                        >
                            Save
                        </LemonButton>
                    </div>
                </div>
            </Form>
        </SceneContent>
    )
}
