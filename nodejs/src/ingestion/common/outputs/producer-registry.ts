import { KafkaProducerRegistryBuilder } from '../../outputs/kafka-producer-registry-builder'
import {
    DEFAULT_PRODUCER,
    DEFAULT_PRODUCER_CONFIG_MAP,
    WARPSTREAM_PRODUCER,
    WARPSTREAM_PRODUCER_CONFIG_MAP,
} from './producers'

/** Register all producers on the builder. Call `.build(config)` to resolve. */
export function createRegistry(kafkaClientRack: string | undefined) {
    return new KafkaProducerRegistryBuilder(kafkaClientRack)
        .register(DEFAULT_PRODUCER, DEFAULT_PRODUCER_CONFIG_MAP)
        .register(WARPSTREAM_PRODUCER, WARPSTREAM_PRODUCER_CONFIG_MAP)
}
