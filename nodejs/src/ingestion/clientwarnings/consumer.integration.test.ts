import { mockProducerObserver } from '~/tests/helpers/mocks/producer.mock'

import { DateTime } from 'luxon'
import { Message } from 'node-rdkafka'

import { getFirstTeam, resetTestDatabase } from '~/tests/helpers/sql'

import { KAFKA_EVENTS_PLUGIN_INGESTION_DLQ, KAFKA_INGESTION_WARNINGS } from '../../config/kafka-topics'
import { KafkaProducerWrapper } from '../../kafka/producer'
import { Hub, PipelineEvent, Team } from '../../types'
import { closeHub, createHub } from '../../utils/db/hub'
import { parseJSON } from '../../utils/json-parse'
import { UUIDT } from '../../utils/utils'
import { DLQ_OUTPUT, INGESTION_WARNINGS_OUTPUT } from '../common/outputs'
import { IngestionOutputs } from '../outputs/ingestion-outputs'
import { ClientWarningsConsumer } from './consumer'

function createTestClientWarningsOutputs(kafkaProducer: KafkaProducerWrapper) {
    return new IngestionOutputs({
        [INGESTION_WARNINGS_OUTPUT]: [
            { topic: KAFKA_INGESTION_WARNINGS, producer: kafkaProducer, producerName: 'test' },
        ],
        [DLQ_OUTPUT]: [{ topic: KAFKA_EVENTS_PLUGIN_INGESTION_DLQ, producer: kafkaProducer, producerName: 'test' }],
    })
}

jest.setTimeout(5000)

jest.mock('../../utils/posthog', () => {
    const original = jest.requireActual('../../utils/posthog')
    return {
        ...original,
        captureException: jest.fn(),
    }
})

jest.mock('../../utils/token-bucket', () => {
    const mockConsume = jest.fn().mockReturnValue(true)
    return {
        ...jest.requireActual('../../utils/token-bucket'),
        IngestionWarningLimiter: {
            consume: mockConsume,
        },
    }
})

let offsetIncrementer = 0

function createKafkaMessage(event: PipelineEvent, token: string): Message {
    const captureEvent = {
        uuid: event.uuid,
        distinct_id: event.distinct_id,
        ip: event.ip,
        now: event.now,
        token,
        data: JSON.stringify(event),
    }
    return {
        key: `${token}:${event.distinct_id}`,
        value: Buffer.from(JSON.stringify(captureEvent)),
        size: 1,
        topic: 'client_iwarnings_ingestion',
        offset: offsetIncrementer++,
        partition: 0,
        timestamp: Date.now(),
        headers: [
            { token: Buffer.from(token) },
            { event: Buffer.from(event.event || '') },
            { uuid: Buffer.from(event.uuid || '') },
            { now: Buffer.from(event.now || '') },
        ],
    }
}

describe('ClientWarningsConsumer', () => {
    let consumer: ClientWarningsConsumer
    let hub: Hub
    let team: Team
    let fixedTime: DateTime

    const createConsumer = async (hub: Hub) => {
        const outputs = createTestClientWarningsOutputs(hub.kafkaProducer)
        const consumer = new ClientWarningsConsumer(hub, {
            outputs,
            teamManager: hub.teamManager,
        })
        consumer['consumer']['kafkaConsumer'] = {
            connect: jest.fn(),
            disconnect: jest.fn(),
            isHealthy: jest.fn(),
        } as any
        await consumer.start()
        return consumer
    }

    const createEvent = (event?: Partial<PipelineEvent>): PipelineEvent => ({
        distinct_id: 'user-1',
        uuid: new UUIDT().toString(),
        ip: '127.0.0.1',
        site_url: 'us.posthog.com',
        now: fixedTime.toISO()!,
        event: '$$client_ingestion_warning',
        ...event,
        properties: {
            $$client_ingestion_warning_message: 'test warning',
            ...(event?.properties || {}),
        },
    })

    const createKafkaMessages = (events: PipelineEvent[]): Message[] => {
        return events.map((event) => createKafkaMessage(event, team.api_token))
    }

    beforeEach(async () => {
        fixedTime = DateTime.fromObject({ year: 2025, month: 1, day: 1 }, { zone: 'UTC' })
        jest.spyOn(Date, 'now').mockReturnValue(fixedTime.toMillis())
        jest.spyOn(Date.prototype, 'toISOString').mockReturnValue(fixedTime.toISO()!)

        offsetIncrementer = 0
        await resetTestDatabase()
        hub = await createHub()

        team = await getFirstTeam(hub.postgres)
        consumer = await createConsumer(hub)
    })

    afterEach(async () => {
        await consumer.stop()
        await closeHub(hub)
    })

    afterAll(() => {
        jest.useRealTimers()
    })

    it('should produce client ingestion warning to the ingestion_warnings topic', async () => {
        const events = [createEvent()]
        await consumer['consumer'].handleKafkaBatch(createKafkaMessages(events))

        const allMessages = mockProducerObserver.getProducedKafkaMessages()
        const warningMessages = allMessages.filter((m) => m.topic === 'clickhouse_ingestion_warnings_test')
        expect(warningMessages).toHaveLength(1)
    })

    it('should include the warning message in the produced event', async () => {
        const events = [
            createEvent({
                properties: { $$client_ingestion_warning_message: 'payload too large' },
            }),
        ]
        await consumer['consumer'].handleKafkaBatch(createKafkaMessages(events))

        const warningMessages = mockProducerObserver
            .getProducedKafkaMessages()
            .filter((m) => m.topic === 'clickhouse_ingestion_warnings_test')

        expect(warningMessages).toHaveLength(1)
        const details = parseJSON(warningMessages[0].value['details'] as string)
        expect(details.message).toBe('payload too large')
    })

    it('should drop events with unknown tokens', async () => {
        const events = [createEvent()]
        const messages = events.map((event) => createKafkaMessage(event, 'invalid_token'))
        await consumer['consumer'].handleKafkaBatch(messages)

        const allMessages = mockProducerObserver.getProducedKafkaMessages()
        const warningMessages = allMessages.filter((m) => m.topic === 'clickhouse_ingestion_warnings_test')
        expect(warningMessages).toHaveLength(0)
    })
})
