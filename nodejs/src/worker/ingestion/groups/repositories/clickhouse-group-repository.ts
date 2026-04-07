import { DateTime } from 'luxon'

import { Properties } from '~/plugin-scaffold'

import { GROUPS_OUTPUT, GroupsOutput } from '../../../../ingestion/common/outputs'
import { IngestionOutputs } from '../../../../ingestion/outputs/ingestion-outputs'
import { GroupTypeIndex, TeamId, TimestampFormat } from '../../../../types'
import { castTimestampOrNow } from '../../../../utils/utils'

export class ClickhouseGroupRepository {
    private outputs: IngestionOutputs<GroupsOutput>
    constructor(outputs: IngestionOutputs<GroupsOutput>) {
        this.outputs = outputs
    }

    public async upsertGroup(
        teamId: TeamId,
        groupTypeIndex: GroupTypeIndex,
        groupKey: string,
        properties: Properties,
        createdAt: DateTime,
        version: number
    ): Promise<void> {
        await this.outputs.queueMessages(GROUPS_OUTPUT, [
            {
                value: Buffer.from(
                    JSON.stringify({
                        group_type_index: groupTypeIndex,
                        group_key: groupKey,
                        team_id: teamId,
                        group_properties: JSON.stringify(properties),
                        created_at: castTimestampOrNow(createdAt, TimestampFormat.ClickHouseSecondPrecision),
                        version,
                    })
                ),
            },
        ])
    }
}
