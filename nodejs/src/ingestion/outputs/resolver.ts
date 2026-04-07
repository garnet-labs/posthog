import { DualWriteIngestionOutput } from './dual-write-ingestion-output'
import { IngestionOutput } from './ingestion-output'
import { IngestionOutputs } from './ingestion-outputs'
import { KafkaProducerRegistry } from './kafka-producer-registry'
import { SingleIngestionOutput } from './single-ingestion-output'

/**
 * Static definition of an ingestion output.
 *
 * Specifies the default topic and producer, plus env var names for overriding each at deploy time.
 *
 * Optionally specifies env var names for a secondary target (topic + producer on a different broker).
 * When the secondary topic env var is set at runtime, produces will fan out to both targets.
 */
export interface IngestionOutputDefinition<P extends string> {
    defaultTopic: string
    defaultProducerName: P
    /** Env var name to override the producer for this output. */
    producerOverrideEnvVar: string
    /** Env var name to override the topic for this output. */
    topicOverrideEnvVar: string
    /** Env var name for a secondary topic. When set, enables dual writes. */
    secondaryTopicEnvVar?: string
    /** Env var name for the secondary producer. Required when secondaryTopicEnvVar is set. */
    secondaryProducerEnvVar?: string
}

/**
 * One-time factory that builds an `IngestionOutputs` from static definitions and a producer registry.
 *
 * For each output, resolves the producer (with env var override) and topic (with env var override).
 * Throws if any producer is unknown.
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

        const primary = new SingleIngestionOutput(outputName, topic, registry.getProducer(producerName), producerName)

        const secondaryTopic = definition.secondaryTopicEnvVar
            ? process.env[definition.secondaryTopicEnvVar]
            : undefined
        const secondaryProducerName = definition.secondaryProducerEnvVar
            ? (process.env[definition.secondaryProducerEnvVar] as P | undefined)
            : undefined

        if (secondaryTopic && secondaryProducerName) {
            resolved[outputName] = new DualWriteIngestionOutput(
                primary,
                new SingleIngestionOutput(
                    outputName,
                    secondaryTopic,
                    registry.getProducer(secondaryProducerName),
                    secondaryProducerName
                )
            )
        } else {
            resolved[outputName] = primary
        }
    }

    // Safe cast: every key in Record<O, ...> has been resolved above.
    return new IngestionOutputs<O>(resolved as Record<O, IngestionOutput>)
}
