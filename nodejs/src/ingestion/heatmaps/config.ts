import { KAFKA_HEATMAPS_INGESTION, KAFKA_HEATMAPS_INGESTION_DLQ } from '../../config/kafka-topics'
import { IngestionLane } from '../config'

export type HeatmapsConsumerConfig = {
    HEATMAPS_CONSUMER_GROUP_ID: string
    HEATMAPS_CONSUMER_CONSUME_TOPIC: string
    HEATMAPS_CONSUMER_DLQ_TOPIC: string

    /** Pipeline name for metrics labeling */
    INGESTION_PIPELINE: string | null
    /** Lane identifier (main, overflow) for metrics labeling */
    INGESTION_LANE: IngestionLane | null
}

export function getDefaultHeatmapsConsumerConfig(): HeatmapsConsumerConfig {
    return {
        HEATMAPS_CONSUMER_GROUP_ID: 'heatmaps_ingestion',
        HEATMAPS_CONSUMER_CONSUME_TOPIC: KAFKA_HEATMAPS_INGESTION,
        HEATMAPS_CONSUMER_DLQ_TOPIC: KAFKA_HEATMAPS_INGESTION_DLQ,
        INGESTION_PIPELINE: null,
        INGESTION_LANE: null,
    }
}
