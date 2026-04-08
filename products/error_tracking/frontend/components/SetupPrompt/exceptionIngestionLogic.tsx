import { afterMount, kea, path } from 'kea'
import { loaders } from 'kea-loaders'

import api, { ApiRequest } from 'lib/api'
import { isDefinitionStale } from 'lib/utils/definitions'

import { EventDefinitionType } from '~/types'

import type { exceptionIngestionLogicType } from './exceptionIngestionLogicType'

export const exceptionIngestionLogic = kea<exceptionIngestionLogicType>([
    path(['products', 'error_tracking', 'components', 'SetupPrompt', 'exceptionIngestionLogic']),
    loaders({
        hasSentExceptionEvent: {
            __default: undefined as boolean | undefined,
            loadExceptionIngestionState: async (): Promise<boolean> => {
                const [exceptionDefinition, issues] = await Promise.all([
                    api.eventDefinitions.list({
                        event_type: EventDefinitionType.Event,
                        search: '$exception',
                    }),
                    new ApiRequest().errorTrackingIssues().withQueryString({ limit: 1 }).get(),
                ])

                const definition = exceptionDefinition.results.find((r) => r.name === '$exception')
                const hasFreshExceptionDefinition = definition ? !isDefinitionStale(definition) : false
                const hasIssues = Array.isArray(issues.results) && issues.results.length > 0

                return hasFreshExceptionDefinition || hasIssues
            },
        },
    }),

    afterMount(({ actions }) => {
        actions.loadExceptionIngestionState()
    }),
])
