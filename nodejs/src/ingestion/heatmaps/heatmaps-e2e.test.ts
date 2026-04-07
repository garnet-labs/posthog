import { DateTime } from 'luxon'
import { Message } from 'node-rdkafka'
import { v4 } from 'uuid'

import { waitForExpect } from '~/tests/helpers/expectations'
import { resetKafka } from '~/tests/helpers/kafka'

import { Clickhouse } from '../../../tests/helpers/clickhouse'
import { createTestHeatmapsOutputs } from '../../../tests/helpers/ingestion-outputs'
import { createUserTeamAndOrganization, resetTestDatabase } from '../../../tests/helpers/sql'
import { KAFKA_INGESTION_WARNINGS } from '../../config/kafka-topics'
import { KafkaProducerWrapper } from '../../kafka/producer'
import { Hub, PipelineEvent, PluginsServerConfig, ProjectId, Team } from '../../types'
import { closeHub, createHub } from '../../utils/db/hub'
import { UUIDT } from '../../utils/utils'
import { HeatmapsConsumer } from './heatmaps-consumer'

jest.mock('../../utils/logger')

const DEFAULT_TEAM: Team = {
    id: 2,
    project_id: 2 as ProjectId,
    organization_id: '2',
    uuid: v4(),
    name: '2',
    anonymize_ips: true,
    api_token: 'api_token',
    secret_api_token: null,
    slack_incoming_webhook: 'slack_incoming_webhook',
    session_recording_opt_in: true,
    person_processing_opt_out: null,
    heatmaps_opt_in: null,
    ingested_event: true,
    person_display_name_properties: null,
    test_account_filters: null,
    cookieless_server_hash_mode: null,
    timezone: 'UTC',
    available_features: [],
    drop_events_older_than_seconds: null,
    extra_settings: null,
}

let offsetIncrementer = 0
let currentToken: string

class EventBuilder {
    private event: Partial<PipelineEvent> = {}

    constructor(team: Team, distinctId: string = new UUIDT().toString()) {
        this.event = {
            event: '$$heatmap',
            properties: {},
            timestamp: new Date().toISOString(),
            now: new Date().toISOString(),
            ip: null,
            site_url: 'https://example.com',
            uuid: new UUIDT().toString(),
        }
        this.event.distinct_id = distinctId
        this.event.team_id = team.id
    }

    withProperties(properties: Record<string, any>) {
        this.event.properties = properties
        return this
    }

    build(): PipelineEvent {
        return this.event as PipelineEvent
    }
}

const createKafkaMessage = (event: PipelineEvent, timestamp: number = DateTime.now().toMillis()): Message => {
    const token = currentToken
    const captureEvent = {
        uuid: event.uuid,
        distinct_id: event.distinct_id,
        ip: event.ip,
        now: event.now,
        token,
        data: JSON.stringify(event),
    }

    const headers: { [key: string]: Buffer }[] = [
        { token: Buffer.from(token) },
        { distinct_id: Buffer.from(event.distinct_id!) },
    ]
    if (event.timestamp) {
        const timestampMs = DateTime.fromISO(event.timestamp).toMillis()
        headers.push({ timestamp: Buffer.from(timestampMs.toString()) })
    }
    if (event.now) {
        headers.push({ now: Buffer.from(event.now) })
    }

    return {
        key: `${token}:${event.distinct_id}`,
        value: Buffer.from(JSON.stringify(captureEvent)),
        size: 1,
        topic: 'test',
        offset: offsetIncrementer++,
        timestamp: timestamp + offsetIncrementer,
        partition: 1,
        headers,
    }
}

const createKafkaMessages = (events: PipelineEvent[]): Message[] => {
    return events.map((e) => createKafkaMessage(e))
}

const createTestWithHeatmapsConsumer = (baseConfig: Partial<PluginsServerConfig> = {}) => {
    return (
        name: string,
        config: { teamOverrides?: Partial<Team>; pluginServerConfig?: Partial<PluginsServerConfig> } = {},
        testFn: (consumer: HeatmapsConsumer, hub: Hub, team: Team) => Promise<void>
    ) => {
        test(name, async () => {
            const hub = await createHub({
                APP_METRICS_FLUSH_FREQUENCY_MS: 0,
                ...baseConfig,
                ...config.pluginServerConfig,
            })

            const teamId = Math.floor((Date.now() % 1000000000) + Math.random() * 1000000)
            const userId = teamId
            const organizationId = new UUIDT().toString()

            const newTeam: Team = {
                ...DEFAULT_TEAM,
                id: teamId,
                project_id: teamId as ProjectId,
                organization_id: organizationId,
                uuid: v4(),
                name: teamId.toString(),
                ...config.teamOverrides,
            }
            const userUuid = new UUIDT().toString()
            const organizationMembershipId = new UUIDT().toString()

            await createUserTeamAndOrganization(
                hub.postgres,
                newTeam.id,
                userId,
                userUuid,
                newTeam.organization_id,
                organizationMembershipId,
                config.teamOverrides
            )

            const fetchedTeam = await hub.teamManager.getTeam(newTeam.id)
            if (!fetchedTeam) {
                throw new Error(`Failed to fetch team ${newTeam.id} from database`)
            }

            const outputs = createTestHeatmapsOutputs(hub.kafkaProducer)

            const consumer = new HeatmapsConsumer(
                {
                    groupId: 'test-heatmaps',
                    topic: 'test',
                    pipeline: 'heatmaps',
                },
                {
                    outputs,
                    teamManager: hub.teamManager,
                }
            )
            // Skip kafka instantiation for faster tests
            consumer['kafkaConsumer'] = {
                connect: jest.fn(),
                disconnect: jest.fn(),
                isHealthy: jest.fn(),
            } as any

            currentToken = fetchedTeam.api_token
            await consumer.start()
            await testFn(consumer, hub, fetchedTeam)
            await consumer.stop()
            await closeHub(hub)
        })
    }
}

async function waitForClickHouseKafkaConsumer(clickhouse: Clickhouse): Promise<void> {
    const producer = await KafkaProducerWrapper.create(undefined)
    const probeTeamId = -1

    try {
        await waitForExpect(async () => {
            await producer.queueMessages({
                topic: KAFKA_INGESTION_WARNINGS,
                messages: [
                    {
                        value: JSON.stringify({
                            team_id: probeTeamId,
                            type: 'probe',
                            source: 'test-warmup',
                            details: '{}',
                            timestamp: DateTime.utc().toFormat('yyyy-MM-dd HH:mm:ss'),
                        }),
                    },
                ],
            })
            await producer.flush()

            const result = await clickhouse.query<{ count: number }>(
                `SELECT count() as count FROM ingestion_warnings WHERE team_id = ${probeTeamId}`
            )
            expect(Number(result[0]?.count ?? 0)).toBeGreaterThan(0)
        }, 30_000)
    } finally {
        await producer.disconnect()
    }
}

const waitForKafkaMessages = async (hub: Hub) => {
    await hub.kafkaProducer.flush()
}

describe('Heatmaps Pipeline E2E tests', () => {
    const testWithHeatmapsConsumer = createTestWithHeatmapsConsumer()
    let clickhouse: Clickhouse

    beforeAll(async () => {
        clickhouse = Clickhouse.create()
        await resetKafka()
        await resetTestDatabase()
        await clickhouse.resetTestDatabase()
        await waitForClickHouseKafkaConsumer(clickhouse)
    })

    afterAll(async () => {
        await resetTestDatabase()
        await clickhouse.resetTestDatabase()
        clickhouse.close()
    })

    testWithHeatmapsConsumer(
        'should drop $$heatmap events when team.heatmaps_opt_in=false',
        { teamOverrides: { heatmaps_opt_in: false } },
        async (consumer, hub, team) => {
            const distinctId = new UUIDT().toString()
            await consumer.handleKafkaBatch(
                createKafkaMessages([
                    new EventBuilder(team, distinctId)
                        .withProperties({
                            $heatmap_data: {
                                'http://localhost:3000/': [{ x: 100, y: 200, target_fixed: false, type: 'click' }],
                            },
                        })
                        .build(),
                ])
            )

            await waitForKafkaMessages(hub)
            await waitForExpect(async () => {
                const heatmapEvents = await clickhouse.query<{ count: number }>(
                    `SELECT count() as count FROM heatmaps WHERE team_id = ${team.id}`
                )
                expect(Number(heatmapEvents[0]?.count ?? 0)).toBe(0)
            })
        }
    )

    testWithHeatmapsConsumer(
        'should process $$heatmap events when team.heatmaps_opt_in=true',
        { teamOverrides: { heatmaps_opt_in: true } },
        async (consumer, hub, team) => {
            const distinctId = new UUIDT().toString()
            await consumer.handleKafkaBatch(
                createKafkaMessages([
                    new EventBuilder(team, distinctId)
                        .withProperties({
                            $heatmap_data: {
                                'http://localhost:3000/': [{ x: 100, y: 200, target_fixed: false, type: 'click' }],
                            },
                            $viewport_height: 800,
                            $viewport_width: 1200,
                            $session_id: 'test-session',
                        })
                        .build(),
                ])
            )

            await waitForKafkaMessages(hub)
            await waitForExpect(async () => {
                const heatmapEvents = await clickhouse.query<{ count: number }>(
                    `SELECT count() as count FROM heatmaps WHERE team_id = ${team.id}`
                )
                expect(Number(heatmapEvents[0]?.count ?? 0)).toBeGreaterThan(0)
            })
        }
    )
})
