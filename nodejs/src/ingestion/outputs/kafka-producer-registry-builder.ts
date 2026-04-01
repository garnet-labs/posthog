import { ProducerGlobalConfig } from 'node-rdkafka'

import { KafkaProducerWrapper } from '../../kafka/producer'
import { logger } from '../../utils/logger'
import { AllowedConfigKey, parseProducerConfig } from './kafka-producer-config'
import { KafkaProducerRegistry } from './kafka-producer-registry'

const SENSITIVE_KEYS = new Set([
    'sasl.password',
    'sasl.oauthbearer.client.secret',
    'ssl.key.password',
    'ssl.key.pem',
    'ssl.certificate.pem',
])

function redactConfig(config: ProducerGlobalConfig): Record<string, unknown> {
    return Object.fromEntries(Object.entries(config).map(([k, v]) => [k, SENSITIVE_KEYS.has(k) ? '***' : v]))
}

/**
 * Builder for `KafkaProducerRegistry` that validates config keys at compile time.
 *
 * Each `register()` call adds a named producer, mapping rdkafka config keys to config object
 * keys. The compiler verifies that every referenced key exists in the passed config object.
 * The producer name is accumulated in the `P` type parameter.
 *
 * Call `build()` after registering all producers to create the registry. This connects to
 * brokers, so it is async and will throw if any producer fails to connect.
 *
 * @example
 * ```ts
 * const registry = await new KafkaProducerRegistryBuilder(config.KAFKA_CLIENT_RACK)
 *     .register('DEFAULT', DEFAULT_PRODUCER_CONFIG_MAP, config)
 *     .build()
 * // registry is KafkaProducerRegistry<'DEFAULT'>
 * ```
 */
export class KafkaProducerRegistryBuilder<P extends string = never> {
    private registered = new Map<string, ProducerGlobalConfig>()

    constructor(private kafkaClientRack: string | undefined) {}

    /**
     * Register a producer with a name, rdkafka-to-config-key mapping, and config object.
     *
     * The `configMap` maps rdkafka config keys (e.g. `'linger.ms'`) to config key names
     * (e.g. `'KAFKA_PRODUCER_LINGER_MS'`). The config object must contain all referenced
     * keys — this is enforced at compile time via `Record<ConfigKeys, string>`.
     *
     * @param name - Unique producer name (used as the type-level key).
     * @param configMap - Maps rdkafka config keys to config key names.
     * @param config - Config object that must contain all keys referenced by `configMap`.
     */
    register<Name extends string, ConfigKeys extends string>(
        name: Name,
        configMap: Partial<Record<AllowedConfigKey, ConfigKeys>>,
        config: Record<ConfigKeys, string>
    ): KafkaProducerRegistryBuilder<P | Name> {
        const values: Record<string, string> = {}
        for (const [rdkafkaKey, configKey] of Object.entries(configMap)) {
            if (configKey !== undefined) {
                const value = config[configKey]
                if (value) {
                    values[rdkafkaKey] = value
                }
            }
        }
        const resolvedConfig = parseProducerConfig(values)

        const next = new KafkaProducerRegistryBuilder<P | Name>(this.kafkaClientRack)
        next.registered = new Map(this.registered)
        next.registered.set(name, resolvedConfig)
        return next
    }

    /**
     * Create all registered producers and return an immutable registry.
     *
     * Connects to brokers in parallel. Throws if any producer fails to connect.
     */
    async build(): Promise<KafkaProducerRegistry<P>> {
        const producers: Record<string, KafkaProducerWrapper> = {}

        await Promise.all(
            Array.from(this.registered.entries()).map(async ([name, config]) => {
                logger.info('📝', `Creating producer "${name}"`, { config: redactConfig(config) })
                producers[name] = await KafkaProducerWrapper.createWithConfig(this.kafkaClientRack, config)
            })
        )

        // TypeScript cannot verify that an imperatively-built Record has all keys of a
        // generic union P. The builder guarantees this: every `register()` call adds an
        // entry to `this.registered`, and `build()` creates a producer for each entry.
        return new KafkaProducerRegistry<P>(producers as Record<P, KafkaProducerWrapper>)
    }
}
