import { DateTime } from 'luxon'

import { PluginEvent, Properties } from '~/plugin-scaffold'

import { PersonDistinctIdsOutput, PersonsOutput } from '../../../ingestion/analytics/outputs'
import { IngestionWarningsOutput } from '../../../ingestion/common/outputs'
import { IngestionOutputs } from '../../../ingestion/outputs/ingestion-outputs'
import { Team } from '../../../types'
import { MergeMode } from './person-merge-types'
import { PersonMessage } from './person-message'
import { PersonsStore } from './persons-store'

export type PersonOutputs = IngestionOutputs<PersonsOutput | PersonDistinctIdsOutput | IngestionWarningsOutput>

/**
 * Lightweight data holder containing all the context needed for person processing.
 * This replaces the previous PersonState class which mixed data and business logic.
 */
export class PersonContext {
    public readonly eventProperties: Properties
    public updateIsIdentified: boolean = false

    public readonly event: PluginEvent
    public readonly team: Team
    public readonly distinctId: string
    public readonly timestamp: DateTime
    public readonly processPerson: boolean
    public readonly outputs: PersonOutputs
    public readonly personStore: PersonsStore
    public readonly measurePersonJsonbSize: number
    public readonly mergeMode: MergeMode
    public readonly updateAllProperties: boolean
    public readonly shouldUpdateLastSeenAt: boolean

    constructor(
        event: PluginEvent,
        team: Team,
        distinctId: string,
        timestamp: DateTime,
        processPerson: boolean,
        outputs: PersonOutputs,
        personStore: PersonsStore,
        measurePersonJsonbSize: number = 0,
        mergeMode: MergeMode,
        updateAllProperties: boolean = false,
        shouldUpdateLastSeenAt: boolean = false
    ) {
        this.event = event
        this.team = team
        this.distinctId = distinctId
        this.timestamp = timestamp
        this.processPerson = processPerson
        this.outputs = outputs
        this.personStore = personStore
        this.measurePersonJsonbSize = measurePersonJsonbSize
        this.mergeMode = mergeMode
        this.updateAllProperties = updateAllProperties
        this.shouldUpdateLastSeenAt = shouldUpdateLastSeenAt
        this.eventProperties = event.properties!
    }

    async produceMessages(messages: PersonMessage[]): Promise<void> {
        await Promise.all(messages.map((msg) => this.outputs.produce(msg.output, { value: msg.value, key: null })))
    }
}
