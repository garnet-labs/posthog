import { hostname } from 'os'

import { AllowedConfigKey, getProducerConfig } from './kafka-producer-config'

const TEST_CONFIG_MAP: Partial<Record<AllowedConfigKey, string>> = {
    'metadata.broker.list': 'TEST_BROKER',
    'security.protocol': 'TEST_SECURITY_PROTOCOL',
    'compression.codec': 'TEST_COMPRESSION',
    'linger.ms': 'TEST_LINGER',
    'batch.size': 'TEST_BATCH_SIZE',
    'enable.ssl.certificate.verification': 'TEST_SSL_VERIFY',
}

describe('getProducerConfig', () => {
    it('returns defaults when no config values are set', () => {
        const config = getProducerConfig(TEST_CONFIG_MAP, {})

        expect(config).toEqual({
            'client.id': hostname(),
            'metadata.broker.list': 'kafka:9092',
            'compression.codec': 'snappy',
            'linger.ms': 20,
            'batch.size': 8 * 1024 * 1024,
            'queue.buffering.max.messages': 100_000,
            log_level: 4,
            'enable.idempotence': true,
            'metadata.max.age.ms': 30000,
            'retry.backoff.ms': 500,
            'socket.timeout.ms': 30000,
            'max.in.flight.requests.per.connection': 5,
        })
    })

    it('overrides defaults with config values', () => {
        const config = getProducerConfig(TEST_CONFIG_MAP, {
            TEST_BROKER: 'broker1:9092,broker2:9092',
            TEST_COMPRESSION: 'gzip',
            TEST_LINGER: '50',
        })

        expect(config['metadata.broker.list']).toBe('broker1:9092,broker2:9092')
        expect(config['compression.codec']).toBe('gzip')
        expect(config['linger.ms']).toBe(50)
    })

    it('coerces numeric values', () => {
        const config = getProducerConfig(TEST_CONFIG_MAP, {
            TEST_LINGER: '100',
            TEST_BATCH_SIZE: '4194304',
        })

        expect(config['linger.ms']).toBe(100)
        expect(config['batch.size']).toBe(4194304)
    })

    it('parses boolean values', () => {
        const config = getProducerConfig(TEST_CONFIG_MAP, {
            TEST_SSL_VERIFY: 'false',
        })

        expect(config['enable.ssl.certificate.verification']).toBe(false)
    })

    it('throws on invalid enum values', () => {
        expect(() =>
            getProducerConfig(TEST_CONFIG_MAP, {
                TEST_SECURITY_PROTOCOL: 'invalid_protocol',
            })
        ).toThrow()
    })

    it('throws on invalid boolean values', () => {
        expect(() =>
            getProducerConfig(TEST_CONFIG_MAP, {
                TEST_SSL_VERIFY: 'maybe',
            })
        ).toThrow()
    })

    it('always sets client.id to hostname', () => {
        const config = getProducerConfig(TEST_CONFIG_MAP, {})

        expect(config['client.id']).toBe(hostname())
    })

    it('ignores config fields not in the config map', () => {
        const config = getProducerConfig(TEST_CONFIG_MAP, {
            TEST_UNKNOWN_SETTING: 'value',
        })

        expect(config).not.toHaveProperty('unknown.setting')
    })

    it('treats empty string values as unset', () => {
        const config = getProducerConfig(TEST_CONFIG_MAP, {
            TEST_BROKER: '',
            TEST_LINGER: '',
        })

        expect(config['metadata.broker.list']).toBe('kafka:9092')
        expect(config['linger.ms']).toBe(20)
    })
})
