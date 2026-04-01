import {
    KAFKA_APP_METRICS_2,
    KAFKA_CLICKHOUSE_TOPHOG,
    KAFKA_ERROR_TRACKING_INGESTION,
    KAFKA_ERROR_TRACKING_INGESTION_DLQ,
    KAFKA_ERROR_TRACKING_INGESTION_OVERFLOW,
    KAFKA_EVENTS_JSON,
    KAFKA_INGESTION_WARNINGS,
    KAFKA_LOG_ENTRIES,
} from '../../config/kafka-topics'
import { IngestionLane } from '../config'
import { type Infer, env, oneOf, str } from '../utils/config-parser'

export type ErrorTrackingConsumerConfig = {
    ERROR_TRACKING_CONSUMER_GROUP_ID: string
    ERROR_TRACKING_CONSUMER_CONSUME_TOPIC: string
    ERROR_TRACKING_CONSUMER_DLQ_TOPIC: string
    ERROR_TRACKING_CONSUMER_OVERFLOW_TOPIC: string
    ERROR_TRACKING_CONSUMER_OUTPUT_TOPIC: string
    ERROR_TRACKING_CYMBAL_BASE_URL: string
    ERROR_TRACKING_CYMBAL_TIMEOUT_MS: number

    /** Token bucket capacity for rate limiting (events per token:distinct_id) */
    ERROR_TRACKING_OVERFLOW_BUCKET_CAPACITY: number
    /** Token bucket replenish rate (events per second) */
    ERROR_TRACKING_OVERFLOW_BUCKET_REPLENISH_RATE: number
    /** When true, uses Redis to coordinate overflow state across pods */
    ERROR_TRACKING_STATEFUL_OVERFLOW_ENABLED: boolean
    /** TTL in seconds for Redis overflow flags */
    ERROR_TRACKING_STATEFUL_OVERFLOW_REDIS_TTL_SECONDS: number
    /** TTL in seconds for local cache entries */
    ERROR_TRACKING_STATEFUL_OVERFLOW_LOCAL_CACHE_TTL_SECONDS: number

    /** Max HTTP body size in bytes per Cymbal API request. Used to proactively
     *  split large batches before they hit Cymbal's body limit. */
    ERROR_TRACKING_CYMBAL_MAX_BODY_BYTES: number

    /** Pipeline name for metrics labeling */
    INGESTION_PIPELINE: string | null
    /** Lane identifier (main, overflow) for metrics labeling */
    INGESTION_LANE: IngestionLane | null
}

export function getDefaultErrorTrackingConsumerConfig(): ErrorTrackingConsumerConfig {
    return {
        ERROR_TRACKING_CONSUMER_GROUP_ID: 'ingestion-errortracking',
        ERROR_TRACKING_CONSUMER_CONSUME_TOPIC: KAFKA_ERROR_TRACKING_INGESTION,
        ERROR_TRACKING_CONSUMER_DLQ_TOPIC: KAFKA_ERROR_TRACKING_INGESTION_DLQ,
        ERROR_TRACKING_CONSUMER_OVERFLOW_TOPIC: KAFKA_ERROR_TRACKING_INGESTION_OVERFLOW,
        ERROR_TRACKING_CONSUMER_OUTPUT_TOPIC: KAFKA_EVENTS_JSON,
        ERROR_TRACKING_CYMBAL_BASE_URL: 'http://localhost:3302',
        ERROR_TRACKING_CYMBAL_TIMEOUT_MS: 15000,
        ERROR_TRACKING_OVERFLOW_BUCKET_CAPACITY: 1000,
        ERROR_TRACKING_OVERFLOW_BUCKET_REPLENISH_RATE: 1.0,
        ERROR_TRACKING_STATEFUL_OVERFLOW_ENABLED: false,
        ERROR_TRACKING_STATEFUL_OVERFLOW_REDIS_TTL_SECONDS: 300, // 5 minutes
        ERROR_TRACKING_STATEFUL_OVERFLOW_LOCAL_CACHE_TTL_SECONDS: 60, // 1 minute
        ERROR_TRACKING_CYMBAL_MAX_BODY_BYTES: 1_800_000,
        INGESTION_PIPELINE: null,
        INGESTION_LANE: null,
    }
}

// ---------------------------------------------------------------------------
// Error tracking outputs config — Zod schema, type inferred
// ---------------------------------------------------------------------------

export const errorTrackingOutputsConfigSchema = env({
    // ── Kafka producer (DEFAULT) ──────────────────────────────────────────

    KAFKA_PRODUCER_METADATA_BROKER_LIST: str('', 'Broker list for the default Kafka producer'),
    KAFKA_PRODUCER_SECURITY_PROTOCOL: str('', 'Security protocol (plaintext, ssl, sasl_ssl)'),
    KAFKA_PRODUCER_SASL_MECHANISMS: str('', 'SASL mechanism'),
    KAFKA_PRODUCER_SASL_USERNAME: str('', 'SASL username'),
    KAFKA_PRODUCER_SASL_PASSWORD: str('', 'SASL password'),
    KAFKA_PRODUCER_COMPRESSION_CODEC: str('', 'Compression (none, gzip, snappy, lz4, zstd)'),
    KAFKA_PRODUCER_LINGER_MS: str('', 'Producer batching delay (linger.ms)'),
    KAFKA_PRODUCER_BATCH_SIZE: str('', 'Producer batch size (bytes)'),
    KAFKA_PRODUCER_QUEUE_BUFFERING_MAX_MESSAGES: str('', 'Max messages in producer queue'),
    KAFKA_PRODUCER_QUEUE_BUFFERING_MAX_KBYTES: str('', 'Max kbytes in producer queue'),
    KAFKA_PRODUCER_ENABLE_SSL_CERTIFICATE_VERIFICATION: str('', 'Enable SSL cert verification'),
    KAFKA_PRODUCER_ENABLE_IDEMPOTENCE: str('', 'Enable idempotent producer'),
    KAFKA_PRODUCER_MESSAGE_MAX_BYTES: str('', 'Max message size (bytes)'),
    KAFKA_PRODUCER_BATCH_NUM_MESSAGES: str('', 'Max messages per batch'),
    KAFKA_PRODUCER_STICKY_PARTITIONING_LINGER_MS: str('', 'Sticky partitioning delay (ms)'),
    KAFKA_PRODUCER_TOPIC_METADATA_REFRESH_INTERVAL_MS: str('', 'Topic metadata refresh (ms)'),
    KAFKA_PRODUCER_METADATA_MAX_AGE_MS: str('', 'Max cached metadata age (ms)'),
    KAFKA_PRODUCER_RETRIES: str('', 'Max send retries'),
    KAFKA_PRODUCER_MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION: str('', 'Max in-flight requests'),

    // ── Output topics and producers ───────────────────────────────────────

    ERROR_TRACKING_OUTPUT_EVENTS_TOPIC: str(KAFKA_EVENTS_JSON, 'Topic for processed events'),
    ERROR_TRACKING_OUTPUT_EVENTS_PRODUCER: oneOf(['DEFAULT'], 'DEFAULT', 'Producer for events'),
    ERROR_TRACKING_OUTPUT_INGESTION_WARNINGS_TOPIC: str(KAFKA_INGESTION_WARNINGS, 'Topic for ingestion warnings'),
    ERROR_TRACKING_OUTPUT_INGESTION_WARNINGS_PRODUCER: oneOf(['DEFAULT'], 'DEFAULT', 'Producer for warnings'),
    ERROR_TRACKING_OUTPUT_DLQ_TOPIC: str(KAFKA_ERROR_TRACKING_INGESTION_DLQ, 'Dead-letter queue topic'),
    ERROR_TRACKING_OUTPUT_DLQ_PRODUCER: oneOf(['DEFAULT'], 'DEFAULT', 'Producer for DLQ'),
    ERROR_TRACKING_OUTPUT_OVERFLOW_TOPIC: str(KAFKA_ERROR_TRACKING_INGESTION_OVERFLOW, 'Overflow topic'),
    ERROR_TRACKING_OUTPUT_OVERFLOW_PRODUCER: oneOf(['DEFAULT'], 'DEFAULT', 'Producer for overflow'),
    ERROR_TRACKING_OUTPUT_APP_METRICS_TOPIC: str(KAFKA_APP_METRICS_2, 'Topic for app metrics'),
    ERROR_TRACKING_OUTPUT_APP_METRICS_PRODUCER: oneOf(['DEFAULT'], 'DEFAULT', 'Producer for app metrics'),
    ERROR_TRACKING_OUTPUT_LOG_ENTRIES_TOPIC: str(KAFKA_LOG_ENTRIES, 'Topic for log entries'),
    ERROR_TRACKING_OUTPUT_LOG_ENTRIES_PRODUCER: oneOf(['DEFAULT'], 'DEFAULT', 'Producer for log entries'),
    ERROR_TRACKING_OUTPUT_TOPHOG_TOPIC: str(KAFKA_CLICKHOUSE_TOPHOG, 'Topic for TopHog metrics'),
    ERROR_TRACKING_OUTPUT_TOPHOG_PRODUCER: oneOf(['DEFAULT'], 'DEFAULT', 'Producer for TopHog'),
})

export type ErrorTrackingOutputsConfig = Infer<typeof errorTrackingOutputsConfigSchema>

export function parseErrorTrackingOutputsConfig(
    envVars: Record<string, string | undefined> = process.env
): ErrorTrackingOutputsConfig {
    return errorTrackingOutputsConfigSchema.parse(envVars)
}
