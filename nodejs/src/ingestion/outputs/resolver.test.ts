import { KafkaProducerWrapper } from '../../kafka/producer'
import { KafkaProducerRegistry } from './kafka-producer-registry'
import { IngestionOutputDefinition, resolveIngestionOutputs } from './resolver'

describe('resolveIngestionOutputs', () => {
    const OLD_ENV = process.env

    beforeEach(() => {
        jest.resetModules()
        process.env = { ...OLD_ENV }
    })

    afterAll(() => {
        process.env = OLD_ENV
    })

    type TestProducer = 'PRIMARY' | 'SECONDARY'

    function createMockProducer(): KafkaProducerWrapper {
        return {
            produce: jest.fn().mockResolvedValue(undefined),
            queueMessages: jest.fn().mockResolvedValue(undefined),
            checkConnection: jest.fn().mockResolvedValue(undefined),
            checkTopicExists: jest.fn().mockResolvedValue(undefined),
        } as unknown as KafkaProducerWrapper
    }

    function createRegistry(
        producers: Record<TestProducer, KafkaProducerWrapper>
    ): KafkaProducerRegistry<TestProducer> {
        return new KafkaProducerRegistry(producers)
    }

    const testDefinitions: Record<string, IngestionOutputDefinition<TestProducer>> = {
        events: {
            defaultTopic: 'clickhouse_events',
            defaultProducerName: 'PRIMARY',
            producerOverrideEnvVar: 'TEST_EVENTS_PRODUCER',
            topicOverrideEnvVar: 'TEST_EVENTS_TOPIC',
            secondaryTopicEnvVar: 'TEST_EVENTS_SECONDARY_TOPIC',
            secondaryProducerEnvVar: 'TEST_EVENTS_SECONDARY_PRODUCER',
        },
        ai_events: {
            defaultTopic: 'clickhouse_ai_events',
            defaultProducerName: 'PRIMARY',
            producerOverrideEnvVar: 'TEST_AI_EVENTS_PRODUCER',
            topicOverrideEnvVar: 'TEST_AI_EVENTS_TOPIC',
        },
    }

    it('resolves outputs with default topics and producers', async () => {
        const primary = createMockProducer()
        const secondary = createMockProducer()
        const registry = createRegistry({ PRIMARY: primary, SECONDARY: secondary })

        const outputs = resolveIngestionOutputs(registry, testDefinitions)

        await outputs.queueMessages('events', [{ value: Buffer.from('test') }])
        expect(primary.queueMessages).toHaveBeenCalledWith({
            topic: 'clickhouse_events',
            messages: [{ value: Buffer.from('test') }],
        })
    })

    it('overrides topic from env var', async () => {
        process.env.TEST_EVENTS_TOPIC = 'custom_events_topic'
        const primary = createMockProducer()
        const registry = createRegistry({ PRIMARY: primary, SECONDARY: createMockProducer() })

        const outputs = resolveIngestionOutputs(registry, testDefinitions)

        await outputs.queueMessages('events', [{ value: Buffer.from('test') }])
        expect(primary.queueMessages).toHaveBeenCalledWith({
            topic: 'custom_events_topic',
            messages: [{ value: Buffer.from('test') }],
        })
    })

    it('topic override only affects the overridden output', async () => {
        process.env.TEST_EVENTS_TOPIC = 'custom_events_topic'
        const primary = createMockProducer()
        const registry = createRegistry({ PRIMARY: primary, SECONDARY: createMockProducer() })

        const outputs = resolveIngestionOutputs(registry, testDefinitions)

        await outputs.queueMessages('ai_events', [{ value: Buffer.from('test') }])
        expect(primary.queueMessages).toHaveBeenCalledWith({
            topic: 'clickhouse_ai_events',
            messages: [{ value: Buffer.from('test') }],
        })
    })

    it('overrides producer from env var', async () => {
        process.env.TEST_EVENTS_PRODUCER = 'SECONDARY'
        const primary = createMockProducer()
        const secondary = createMockProducer()
        const registry = createRegistry({ PRIMARY: primary, SECONDARY: secondary })

        const outputs = resolveIngestionOutputs(registry, testDefinitions)

        await outputs.queueMessages('events', [{ value: Buffer.from('test') }])
        expect(secondary.queueMessages).toHaveBeenCalledTimes(1)
        expect(primary.queueMessages).not.toHaveBeenCalled()
    })

    it('producer override only affects the overridden output', async () => {
        process.env.TEST_EVENTS_PRODUCER = 'SECONDARY'
        const primary = createMockProducer()
        const secondary = createMockProducer()
        const registry = createRegistry({ PRIMARY: primary, SECONDARY: secondary })

        const outputs = resolveIngestionOutputs(registry, testDefinitions)

        await outputs.queueMessages('ai_events', [{ value: Buffer.from('test') }])
        expect(primary.queueMessages).toHaveBeenCalledTimes(1)
        expect(secondary.queueMessages).not.toHaveBeenCalled()
    })

    it('resolves empty definitions', async () => {
        const registry = createRegistry({ PRIMARY: createMockProducer(), SECONDARY: createMockProducer() })
        const outputs = resolveIngestionOutputs(registry, {})
        await expect(outputs.checkHealth()).resolves.toEqual([])
    })

    describe('secondary targets', () => {
        it('does not add secondary target when env vars are not set', async () => {
            const primary = createMockProducer()
            const secondary = createMockProducer()
            const registry = createRegistry({ PRIMARY: primary, SECONDARY: secondary })

            const outputs = resolveIngestionOutputs(registry, testDefinitions)

            await outputs.produce('events', { value: Buffer.from('test'), key: Buffer.from('key') })
            expect(primary.produce).toHaveBeenCalledTimes(1)
            expect(secondary.produce).not.toHaveBeenCalled()
        })

        it('adds secondary target when both env vars are set', async () => {
            process.env.TEST_EVENTS_SECONDARY_TOPIC = 'events_v2'
            process.env.TEST_EVENTS_SECONDARY_PRODUCER = 'SECONDARY'
            const primary = createMockProducer()
            const secondary = createMockProducer()
            const registry = createRegistry({ PRIMARY: primary, SECONDARY: secondary })

            const outputs = resolveIngestionOutputs(registry, testDefinitions)

            await outputs.produce('events', { value: Buffer.from('test'), key: Buffer.from('key') })
            expect(primary.produce).toHaveBeenCalledWith({
                topic: 'clickhouse_events',
                value: Buffer.from('test'),
                key: Buffer.from('key'),
            })
            expect(secondary.produce).toHaveBeenCalledWith({
                topic: 'events_v2',
                value: Buffer.from('test'),
                key: Buffer.from('key'),
            })
        })

        it('does not add secondary target when only topic env var is set', async () => {
            process.env.TEST_EVENTS_SECONDARY_TOPIC = 'events_v2'
            const primary = createMockProducer()
            const registry = createRegistry({ PRIMARY: primary, SECONDARY: createMockProducer() })

            const outputs = resolveIngestionOutputs(registry, testDefinitions)

            await outputs.produce('events', { value: Buffer.from('test'), key: Buffer.from('key') })
            expect(primary.produce).toHaveBeenCalledTimes(1)
        })

        it('does not add secondary target when only producer env var is set', async () => {
            process.env.TEST_EVENTS_SECONDARY_PRODUCER = 'SECONDARY'
            const primary = createMockProducer()
            const secondary = createMockProducer()
            const registry = createRegistry({ PRIMARY: primary, SECONDARY: secondary })

            const outputs = resolveIngestionOutputs(registry, testDefinitions)

            await outputs.produce('events', { value: Buffer.from('test'), key: Buffer.from('key') })
            expect(primary.produce).toHaveBeenCalledTimes(1)
            expect(secondary.produce).not.toHaveBeenCalled()
        })

        it('secondary target does not affect other outputs', async () => {
            process.env.TEST_EVENTS_SECONDARY_TOPIC = 'events_v2'
            process.env.TEST_EVENTS_SECONDARY_PRODUCER = 'SECONDARY'
            const primary = createMockProducer()
            const secondary = createMockProducer()
            const registry = createRegistry({ PRIMARY: primary, SECONDARY: secondary })

            const outputs = resolveIngestionOutputs(registry, testDefinitions)

            await outputs.produce('ai_events', { value: Buffer.from('test'), key: Buffer.from('key') })
            expect(primary.produce).toHaveBeenCalledTimes(1)
            expect(secondary.produce).not.toHaveBeenCalled()
        })
    })
})
