import { PersonDistinctIdsOutput, PersonsOutput } from '../../../ingestion/analytics/outputs/names'

export type PersonMessage = {
    output: PersonsOutput | PersonDistinctIdsOutput
    value: Buffer | null
}
