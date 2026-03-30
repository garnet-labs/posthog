import { IconList } from '@posthog/icons'

import { ErrorEventProperties, ErrorTrackingRuntime } from 'lib/components/Errors/types'
import { getRuntimeFromLib, stringify } from 'lib/components/Errors/utils'
import { Dayjs, dayjs } from 'lib/dayjs'

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

/**
 * In-memory loader for exception steps (derived from event properties, no API calls).
 */
export class ExceptionStepLoader implements ItemLoader<ExceptionStepItem> {
    private readonly items: ExceptionStepItem[]

    constructor(exceptionUuid: string, exceptionTimestamp: Dayjs, properties?: ErrorEventProperties) {
        this.items = buildExceptionStepItems(exceptionUuid, exceptionTimestamp, properties)
    }

    async loadBefore(cursor: Dayjs, limit: number): Promise<ExceptionStepItem[]> {
        const before = this.items.filter((item) => item.timestamp.isBefore(cursor))
        return before.slice(-limit)
    }

    async loadAfter(cursor: Dayjs, limit: number): Promise<ExceptionStepItem[]> {
        const after = this.items.filter((item) => item.timestamp.isAfter(cursor))
        return after.slice(0, limit)
    }
}

// ─── Step item builders ──────────────────────────────────────────────────────

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
            timestamp: dayjs.utc(exceptionTimestamp).add(offsetMs!, 'millisecond'),
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
