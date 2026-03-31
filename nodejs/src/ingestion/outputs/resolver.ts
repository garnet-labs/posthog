import { IngestionOutput, IngestionOutputs } from './ingestion-outputs'
import { KafkaProducerRegistry } from './kafka-producer-registry'

/**
 * Static definition of an ingestion output.
 *
 * Specifies the default topic and producer, plus config field names for
 * overriding each at deploy time. The field names match env var names so
 * that overrideWithEnv() populates them automatically from the environment.
 */
export interface IngestionOutputDefinition<P extends string> {
    defaultTopic: string
    defaultProducerName: P
    /** Config field name to override the producer for this output. */
    producerOverrideField: string
    /** Config field name to override the topic for this output. */
    topicOverrideField: string
}

/**
 * One-time factory that builds an `IngestionOutputs` from static definitions and a producer registry.
 *
 * For each output, resolves the producer (with config override) and topic (with config override).
 * All producers are resolved in parallel. Throws if any producer creation fails.
 *
 * @param registry - The producer registry to resolve producers from.
 * @param definitions - Static output definitions keyed by output name.
 * @param config - The server config object to read override values from.
 * @returns A fully resolved `IngestionOutputs` instance ready for use by pipeline steps.
 */
export async function resolveIngestionOutputs<O extends string, P extends string>(
    registry: KafkaProducerRegistry<P>,
    definitions: Record<O, IngestionOutputDefinition<P>>,
    config: Record<string, string | number | boolean | null | undefined>
): Promise<IngestionOutputs<O>> {
    const promises: Promise<{ outputName: O; config: IngestionOutput }>[] = []

    for (const outputName in definitions) {
        const definition = definitions[outputName]
        const producerOverride = config[definition.producerOverrideField]
        const producerName = (
            producerOverride && producerOverride !== '' ? producerOverride : definition.defaultProducerName
        ) as P
        const topicOverride = config[definition.topicOverrideField]
        const topic = topicOverride && topicOverride !== '' ? String(topicOverride) : definition.defaultTopic

        // getProducer throws if the producer is not found, so all keys of O
        // are guaranteed to be present in the result or the call fails.
        promises.push(
            registry.getProducer(producerName).then((producer) => ({
                outputName,
                config: { topic, producer },
            }))
        )
    }

    const results = await Promise.all(promises)
    const resolved: Record<string, IngestionOutput> = {}
    for (const { outputName, config } of results) {
        resolved[outputName] = config
    }

    // Safe cast: every key in Record<O, ...> has been resolved above.
    return new IngestionOutputs<O>(resolved as Record<O, IngestionOutput>)
}
