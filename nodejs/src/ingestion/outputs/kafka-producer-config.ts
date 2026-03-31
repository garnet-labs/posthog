import { ProducerGlobalConfig } from 'node-rdkafka'
import { hostname } from 'os'
import { z } from 'zod'

/**
 * Zod schema defining the supported rdkafka producer config keys.
 *
 * Each key has a parser (string, number, enum, boolean) and an optional default.
 * Keys without defaults are optional — they're only included in the config if the
 * corresponding env var is set. Invalid env var values cause a startup failure.
 */
const producerConfigSchema = z.object({
    'metadata.broker.list': z.string().default('kafka:9092'),
    'security.protocol': z.enum(['plaintext', 'ssl', 'sasl_plaintext', 'sasl_ssl']).optional(),
    'sasl.mechanisms': z.string().optional(),
    'sasl.username': z.string().optional(),
    'sasl.password': z.string().optional(),
    'compression.codec': z.enum(['none', 'gzip', 'snappy', 'lz4', 'zstd']).default('snappy'),
    'linger.ms': z.coerce.number().default(20),
    'batch.size': z.coerce.number().default(8 * 1024 * 1024),
    'queue.buffering.max.messages': z.coerce.number().default(100_000),
    'queue.buffering.max.kbytes': z.coerce.number().optional(),
    'enable.ssl.certificate.verification': z
        .enum(['true', 'false'])
        .transform((v) => v === 'true')
        .optional(),
    log_level: z.coerce.number().default(4),
    'enable.idempotence': z
        .enum(['true', 'false'])
        .transform((v) => v === 'true')
        .default('true'),
    'message.max.bytes': z.coerce.number().optional(),
    'batch.num.messages': z.coerce.number().optional(),
    'sticky.partitioning.linger.ms': z.coerce.number().optional(),
    'topic.metadata.refresh.interval.ms': z.coerce.number().optional(),
    'metadata.max.age.ms': z.coerce.number().default(30000),
    'message.send.max.retries': z.coerce.number().optional(),
    'retry.backoff.ms': z.coerce.number().default(500),
    'socket.timeout.ms': z.coerce.number().default(30000),
    'max.in.flight.requests.per.connection': z.coerce.number().default(5),
})

/** The rdkafka config keys that can be configured. */
export type AllowedConfigKey = keyof z.input<typeof producerConfigSchema>

/**
 * Build an rdkafka producer config from a config object.
 *
 * Takes a map of rdkafka config keys to config field names, plus the server
 * config object. Looks up each field name in the config object, filters out
 * empty/missing values, and parses the result through the zod schema. Missing
 * values fall back to schema defaults. Invalid values throw.
 *
 * @param configFieldMap - Maps rdkafka config keys (e.g. `linger.ms`) to
 *   config field names (e.g. `KAFKA_PRODUCER_LINGER_MS`).
 * @param config - The server config object to read values from.
 * @returns A fully typed `ProducerGlobalConfig` with `client.id` set to the hostname.
 */
export function getProducerConfig(
    configFieldMap: Partial<Record<AllowedConfigKey, string>>,
    config: Record<string, string | number | boolean | null | undefined>
): ProducerGlobalConfig {
    const values: Record<string, string> = {}
    for (const configKey in configFieldMap) {
        const fieldName = configFieldMap[configKey as AllowedConfigKey]!
        const value = config[fieldName]
        if (value !== undefined && value !== null && value !== '') {
            values[configKey] = String(value)
        }
    }

    const parsed = producerConfigSchema.parse(values)

    return { 'client.id': hostname(), ...parsed }
}
