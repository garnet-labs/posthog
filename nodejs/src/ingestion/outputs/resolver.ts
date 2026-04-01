import { IngestionOutput, IngestionOutputs } from './ingestion-outputs'
import { KafkaProducerRegistry } from './kafka-producer-registry'

/**
 * Static definition of an ingestion output.
 *
 * Specifies the default topic and producer, plus env var names for overriding each at deploy time.
 */
export interface IngestionOutputDefinition<P extends string> {
    defaultTopic: string
    defaultProducerName: P
    /** Env var name to override the producer for this output. */
    producerOverrideEnvVar: string
    /** Env var name to override the topic for this output. */
    topicOverrideEnvVar: string
}

/**
 * One-time factory that builds an `IngestionOutputs` from static definitions and a producer registry.
 *
 * For each output, resolves the producer (with env var override) and topic (with env var override).
 * All producers are resolved in parallel. Throws if any producer creation fails.
 *
 * @param registry - The producer registry to resolve producers from.
 * @param definitions - Static output definitions keyed by output name.
 * @returns A fully resolved `IngestionOutputs` instance ready for use by pipeline steps.
 */
export function resolveIngestionOutputs<O extends string, P extends string>(
    registry: KafkaProducerRegistry<P>,
    definitions: Record<O, IngestionOutputDefinition<P>>
): IngestionOutputs<O> {
    const resolved: Record<string, IngestionOutput> = {}

    for (const outputName in definitions) {
        const definition = definitions[outputName]
        const producerName = (process.env[definition.producerOverrideEnvVar] ?? definition.defaultProducerName) as P
        const topic = process.env[definition.topicOverrideEnvVar] ?? definition.defaultTopic

        resolved[outputName] = { topic, producer: registry.getProducer(producerName) }
    }

    // Safe cast: every key in Record<O, ...> has been resolved above.
    return new IngestionOutputs<O>(resolved as Record<O, IngestionOutput>)
}
