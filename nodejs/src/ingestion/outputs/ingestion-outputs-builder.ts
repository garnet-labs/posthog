import { IngestionOutput, IngestionOutputs } from './ingestion-outputs'
import { KafkaProducerRegistry } from './kafka-producer-registry'

/**
 * Static definition of an ingestion output — just the config keys for topic and producer.
 *
 * Defaults (topic name, producer name) live in the config object's default values,
 * not in the definition. This keeps definitions pure config-key references.
 */
export interface OutputDefinition<TK extends string, PK extends string> {
    topicKey: TK
    producerKey: PK
}

/**
 * Builder for `IngestionOutputs` that validates config keys at compile time.
 *
 * Each `register()` call adds an output name and its config key requirements to the
 * builder's type parameters. `build(registry, config)` then checks that:
 * - The config contains all accumulated topic keys as `string`
 * - The config contains all accumulated producer keys as `P` (the registry's producer name type)
 *
 * @example
 * ```ts
 * const outputs = new IngestionOutputsBuilder()
 *     .register(EVENTS_OUTPUT, { topicKey: 'OUTPUT_EVENTS_TOPIC', producerKey: 'OUTPUT_EVENTS_PRODUCER' })
 *     .register(DLQ_OUTPUT, { topicKey: 'OUTPUT_DLQ_TOPIC', producerKey: 'OUTPUT_DLQ_PRODUCER' })
 *     .build(registry, config)
 * ```
 */
export class IngestionOutputsBuilder<O extends string = never, TK extends string = never, PK extends string = never> {
    private definitions = new Map<string, { topicKey: TK; producerKey: PK }>()

    /**
     * Register an output with its config key pair.
     *
     * The topic and producer config keys are accumulated in the builder's type parameters
     * and checked against the config object when `build()` is called.
     */
    register<Name extends string, NewTK extends string, NewPK extends string>(
        name: Name,
        definition: OutputDefinition<NewTK, NewPK>
    ): IngestionOutputsBuilder<O | Name, TK | NewTK, PK | NewPK> {
        const next = new IngestionOutputsBuilder<O | Name, TK | NewTK, PK | NewPK>()
        next.definitions = new Map(this.definitions)
        next.definitions.set(name, definition)
        return next
    }

    /**
     * Resolve all registered outputs from the registry and config.
     *
     * The compiler verifies that the config contains all accumulated topic keys as `string`
     * and all accumulated producer keys as `P` (matching the registry's producer name type).
     */
    build<P extends string>(
        registry: KafkaProducerRegistry<P>,
        config: Record<TK, string> & Record<PK, P>
    ): IngestionOutputs<O> {
        const record: Record<string, IngestionOutput> = {}

        for (const [name, def] of this.definitions) {
            record[name] = {
                topic: config[def.topicKey],
                producer: registry.getProducer(config[def.producerKey]),
            }
        }

        // TypeScript cannot verify that an imperatively-built Record has all keys of a
        // generic union O. The builder guarantees this: every register() call adds an
        // entry to definitions, and build() resolves all of them.
        return new IngestionOutputs<O>(record as Record<O, IngestionOutput>)
    }
}
