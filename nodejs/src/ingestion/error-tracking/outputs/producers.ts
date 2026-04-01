import { DEFAULT_PRODUCER, DEFAULT_PRODUCER_CONFIG_MAP } from '../../common/producers'
import { KafkaProducerRegistryBuilder } from '../../outputs/kafka-producer-registry-builder'

export type { DefaultProducer, DefaultProducerConfigKey, ProducerName } from '../../common/producers'

/** Register all producers on the builder. Call `.build(config)` to resolve. */
export function registerProducers(kafkaClientRack: string | undefined) {
    return new KafkaProducerRegistryBuilder(kafkaClientRack).register(DEFAULT_PRODUCER, DEFAULT_PRODUCER_CONFIG_MAP)
}
