import { IconList } from '@posthog/icons'

import { ErrorEventProperties, ErrorTrackingRuntime } from 'lib/components/Errors/types'
import { getRuntimeFromLib, stringify } from 'lib/components/Errors/utils'
import { Dayjs, dayjs } from 'lib/dayjs'
import { TimeTree } from 'lib/utils/time-tree'

import { RuntimeIcon } from 'products/error_tracking/frontend/components/RuntimeIcon'

import { ItemCategory, ItemLoader, ItemRenderer, TimelineItem } from '..'
import { BasePreview } from './base'

type RawExceptionStep = {
    name?: unknown
    type?: unknown
    offset_ms?: unknown
    properties?: unknown
}

export interface ExceptionStepItem extends TimelineItem {
    payload: {
        runtime: ErrorTrackingRuntime
        name: string
        type?: string
        offset_ms?: number
        properties?: Record<string, unknown>
        stepIndex?: number
        malformed?: boolean
        message?: string
        errorMessage?: string
    }
}

export const exceptionStepRenderer: ItemRenderer<ExceptionStepItem> = {
    sourceIcon: ({ item }) => <RuntimeIcon runtime={item.payload.runtime} />,
    categoryIcon: <IconList />,
    render: ({ item }): JSX.Element => {
        if (item.payload.malformed) {
            return (
                <BasePreview
                    name={item.payload.message ?? 'Exception steps unavailable'}
                    description={item.payload.errorMessage}
                    descriptionTitle={item.payload.errorMessage}
                />
            )
        }

        const typeSuffix = item.payload.type ? ` (${item.payload.type})` : ''
        const description = item.payload.properties ? stringify(item.payload.properties) : undefined

        return (
            <BasePreview
                name={`${item.payload.name}${typeSuffix}`}
                description={description}
                descriptionTitle={description}
            />
        )
    },
}

export class ExceptionStepItemLoader implements ItemLoader<ExceptionStepItem> {
    private readonly items: ExceptionStepItem[]
    private readonly cache = new TimeTree<ExceptionStepItem>()
    private hydrated = false

    constructor(exceptionUuid: string, exceptionTimestamp: Dayjs, properties?: ErrorEventProperties) {
        this.items = buildExceptionStepItems(exceptionUuid, exceptionTimestamp, properties)
    }

    clear(): void {
        this.cache.clear()
        this.hydrated = false
    }

    hasPrevious(index: Dayjs): boolean {
        return this.items.some((item) => item.timestamp.isBefore(index))
    }

    hasNext(index: Dayjs): boolean {
        return this.items.some((item) => item.timestamp.isAfter(index))
    }

    async previousBatch(index: Dayjs, count: number): Promise<ExceptionStepItem[]> {
        this.hydrate()
        const all = this.cache.getAll() // sorted ascending
        const before = all.filter((item) => item.timestamp.isBefore(index))
        return before.slice(-count)
    }

    async nextBatch(index: Dayjs, count: number): Promise<ExceptionStepItem[]> {
        this.hydrate()
        const all = this.cache.getAll() // sorted ascending
        const after = all.filter((item) => item.timestamp.isAfter(index))
        return after.slice(0, count)
    }

    private hydrate(): void {
        if (this.hydrated) {
            return
        }
        this.cache.add(this.items)
        this.hydrated = true
    }
}

function buildExceptionStepItems(
    exceptionUuid: string,
    exceptionTimestamp: Dayjs,
    properties?: ErrorEventProperties
): ExceptionStepItem[] {
    const runtime = getRuntimeFromLib(properties?.$lib)
    const rawSteps = properties?.$exception_steps

    if (rawSteps == null) {
        return []
    }

    if (!Array.isArray(rawSteps)) {
        return []
    }

    const validItems: ExceptionStepItem[] = []
    const malformedReasons: string[] = []

    rawSteps.forEach((step, stepIndex) => {
        const result = buildStepItem({
            exceptionUuid,
            exceptionTimestamp,
            runtime,
            step,
            stepIndex,
        })

        if (result.item) {
            validItems.push(result.item)
        } else {
            malformedReasons.push(`step ${stepIndex}: ${result.reason}`)
        }
    })

    if (malformedReasons.length > 0) {
        validItems.push(buildMalformedItem(exceptionUuid, exceptionTimestamp, runtime, malformedReasons.join(', ')))
    }

    return validItems.sort((a, b) => (a.sortPriority ?? 0) - (b.sortPriority ?? 0))
}

type StepBuildResult = { item: ExceptionStepItem; reason?: never } | { item?: never; reason: string }

function buildStepItem({
    exceptionUuid,
    exceptionTimestamp,
    runtime,
    step,
    stepIndex,
}: {
    exceptionUuid: string
    exceptionTimestamp: Dayjs
    runtime: ErrorTrackingRuntime
    step: RawExceptionStep
    stepIndex: number
}): StepBuildResult {
    if (!step || typeof step !== 'object' || Array.isArray(step)) {
        return { reason: 'not an object' }
    }

    const name = typeof step.name === 'string' && step.name.trim() ? step.name : null
    const offsetMs = typeof step.offset_ms === 'number' && Number.isFinite(step.offset_ms) ? step.offset_ms : null

    const missing = [!name && 'name', offsetMs === null && 'offset_ms'].filter(Boolean)
    if (missing.length > 0) {
        return { reason: `missing ${missing.join(', ')}` }
    }

    return {
        item: {
            id: `${exceptionUuid}-exception-step-${stepIndex}`,
            category: ItemCategory.EXCEPTION_STEPS,
            timestamp: dayjs.utc(exceptionTimestamp).add(offsetMs! + stepIndex, 'millisecond'),
            sortPriority: -1000 + stepIndex,
            payload: {
                runtime,
                name: name!,
                type: typeof step.type === 'string' ? step.type : undefined,
                offset_ms: offsetMs!,
                properties: isPlainObject(step.properties) ? step.properties : undefined,
                stepIndex,
            },
        },
    }
}

function buildMalformedItem(
    exceptionUuid: string,
    exceptionTimestamp: Dayjs,
    runtime: ErrorTrackingRuntime,
    errorMessage: string
): ExceptionStepItem {
    return {
        id: `${exceptionUuid}-exception-steps-malformed`,
        category: ItemCategory.EXCEPTION_STEPS,
        timestamp: dayjs.utc(exceptionTimestamp).subtract(1, 'millisecond'),
        sortPriority: -1,
        payload: {
            runtime,
            name: 'Exception steps unavailable',
            malformed: true,
            message: 'Exception steps malformed',
            errorMessage,
        },
    }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
    return !!value && typeof value === 'object' && !Array.isArray(value)
}
