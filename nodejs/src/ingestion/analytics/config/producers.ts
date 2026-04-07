import {
    DEFAULT_PRODUCER,
    DEFAULT_PRODUCER_CONFIG_MAP,
    WARPSTREAM_PRODUCER,
    WARPSTREAM_PRODUCER_CONFIG_MAP,
} from '../../common/producers'
import { KafkaProducerRegistryBuilder } from '../../outputs/kafka-producer-registry-builder'

export type { DefaultProducer, WarpstreamProducer, DefaultProducerConfigKey, ProducerName } from '../../common/producers'

/** Register all producers on the builder. Call `.build(config)` to resolve. */
export function registerProducers(kafkaClientRack: string | undefined) {
    return new KafkaProducerRegistryBuilder(kafkaClientRack)
        .register(DEFAULT_PRODUCER, DEFAULT_PRODUCER_CONFIG_MAP)
        .register(WARPSTREAM_PRODUCER, WARPSTREAM_PRODUCER_CONFIG_MAP)
}
