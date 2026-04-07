import {
    KAFKA_CLICKHOUSE_HEATMAP_EVENTS,
    KAFKA_HEATMAPS_INGESTION_DLQ,
    KAFKA_INGESTION_WARNINGS,
} from '../../../config/kafka-topics'
import { DLQ_OUTPUT, INGESTION_WARNINGS_OUTPUT } from '../../common/outputs'
import { IngestionOutputDefinition } from '../../outputs/resolver'
import { HEATMAPS_OUTPUT } from '../outputs'
import { DEFAULT_PRODUCER, ProducerName } from './producers'

/** Static config for all heatmaps ingestion outputs. */
export const HEATMAPS_OUTPUT_DEFINITIONS: Record<string, IngestionOutputDefinition<ProducerName>> = {
    [HEATMAPS_OUTPUT]: {
        defaultTopic: KAFKA_CLICKHOUSE_HEATMAP_EVENTS,
        defaultProducerName: DEFAULT_PRODUCER,
        producerOverrideEnvVar: 'HEATMAPS_OUTPUT_HEATMAPS_PRODUCER',
        topicOverrideEnvVar: 'HEATMAPS_OUTPUT_HEATMAPS_TOPIC',
        secondaryTopicEnvVar: 'HEATMAPS_OUTPUT_HEATMAPS_SECONDARY_TOPIC',
        secondaryProducerEnvVar: 'HEATMAPS_OUTPUT_HEATMAPS_SECONDARY_PRODUCER',
    },
    [INGESTION_WARNINGS_OUTPUT]: {
        defaultTopic: KAFKA_INGESTION_WARNINGS,
        defaultProducerName: DEFAULT_PRODUCER,
        producerOverrideEnvVar: 'HEATMAPS_OUTPUT_INGESTION_WARNINGS_PRODUCER',
        topicOverrideEnvVar: 'HEATMAPS_OUTPUT_INGESTION_WARNINGS_TOPIC',
        secondaryTopicEnvVar: 'HEATMAPS_OUTPUT_INGESTION_WARNINGS_SECONDARY_TOPIC',
        secondaryProducerEnvVar: 'HEATMAPS_OUTPUT_INGESTION_WARNINGS_SECONDARY_PRODUCER',
    },
    [DLQ_OUTPUT]: {
        defaultTopic: KAFKA_HEATMAPS_INGESTION_DLQ,
        defaultProducerName: DEFAULT_PRODUCER,
        producerOverrideEnvVar: 'HEATMAPS_OUTPUT_DLQ_PRODUCER',
        topicOverrideEnvVar: 'HEATMAPS_OUTPUT_DLQ_TOPIC',
        secondaryTopicEnvVar: 'HEATMAPS_OUTPUT_DLQ_SECONDARY_TOPIC',
        secondaryProducerEnvVar: 'HEATMAPS_OUTPUT_DLQ_SECONDARY_PRODUCER',
    },
}
