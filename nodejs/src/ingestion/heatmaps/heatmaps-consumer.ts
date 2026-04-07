import { Message } from 'node-rdkafka'
import { Gauge } from 'prom-client'

import { instrumentFn } from '~/common/tracing/tracing-utils'

import { KafkaConsumer } from '../../kafka/consumer'
import { HealthCheckResult, PluginServerService } from '../../types'
import { logger } from '../../utils/logger'
import { PromiseScheduler } from '../../utils/promise-scheduler'
import { TeamManager } from '../../utils/team-manager'
import { BatchPipelineUnwrapper } from '../pipelines/batch-pipeline-unwrapper'
import {
    HeatmapsPipelineOutput,
    HeatmapsPipelineOutputs,
    createHeatmapsPipeline,
    runHeatmapsPipeline,
} from './heatmaps-pipeline'

export interface HeatmapsConsumerOptions {
    groupId: string
    topic: string
    pipeline: string
}

export interface HeatmapsConsumerDeps {
    outputs: HeatmapsPipelineOutputs
    teamManager: TeamManager
}

// Useful for consumer lag calculation
const latestOffsetTimestampGauge = new Gauge({
    name: 'heatmaps_latest_processed_timestamp_ms',
    help: 'Timestamp of the latest offset that has been committed.',
    labelNames: ['topic', 'partition', 'groupId'],
    aggregator: 'max',
})

export class HeatmapsConsumer {
    protected name = 'heatmaps-consumer'
    protected kafkaConsumer: KafkaConsumer
    protected pipeline!: BatchPipelineUnwrapper<
        { message: Message },
        HeatmapsPipelineOutput,
        { message: Message },
        never
    >
    protected promiseScheduler: PromiseScheduler

    constructor(
        private config: HeatmapsConsumerOptions,
        private deps: HeatmapsConsumerDeps
    ) {
        this.kafkaConsumer = new KafkaConsumer({
            groupId: config.groupId,
            topic: config.topic,
        })
        this.promiseScheduler = new PromiseScheduler()
    }

    public get service(): PluginServerService {
        return {
            id: this.name,
            onShutdown: async () => await this.stop(),
            healthcheck: () => this.isHealthy(),
        }
    }

    public async start(): Promise<void> {
        logger.info('🚀', `${this.name} - starting`, {
            groupId: this.config.groupId,
            topic: this.config.topic,
        })

        this.pipeline = createHeatmapsPipeline({
            outputs: this.deps.outputs,
            promiseScheduler: this.promiseScheduler,
            teamManager: this.deps.teamManager,
        })

        await this.kafkaConsumer.connect(async (messages) => {
            return await instrumentFn('heatmapsConsumer.handleEachBatch', async () => {
                await this.handleKafkaBatch(messages)
            })
        })

        logger.info('✅', `${this.name} - started`)
    }

    public async stop(): Promise<void> {
        logger.info('🔁', `${this.name} - stopping`)
        await this.promiseScheduler.waitForAll()
        await this.kafkaConsumer.disconnect()
        logger.info('👍', `${this.name} - stopped`)
    }

    public isHealthy(): HealthCheckResult {
        return this.kafkaConsumer.isHealthy()
    }

    public async handleKafkaBatch(messages: Message[]): Promise<void> {
        for (const message of messages) {
            if (message.timestamp) {
                latestOffsetTimestampGauge
                    .labels({ partition: message.partition, topic: message.topic, groupId: this.config.groupId })
                    .set(message.timestamp)
            }
        }

        try {
            await runHeatmapsPipeline(this.pipeline, messages)
        } catch (error) {
            logger.error('❌', `${this.name} - batch processing failed`, {
                error: error instanceof Error ? error.message : String(error),
                size: messages.length,
            })
            throw error
        } finally {
            await this.promiseScheduler.waitForAll()
        }
    }
}
