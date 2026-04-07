import { initializePrometheusLabels } from '../api/router'
import { CommonConfig } from '../common/config'
import { defaultConfig } from '../config/config'
import { createIngestionRedisConnectionConfig } from '../config/redis-pools'
import {
    DatabaseConnectionConfig,
    KafkaBrokerConfig,
    KafkaConsumerBaseConfig,
    RedisConnectionsConfig,
} from '../ingestion/config'
import { HeatmapsConsumerConfig } from '../ingestion/heatmaps/config'
import { HEATMAPS_OUTPUT_DEFINITIONS } from '../ingestion/heatmaps/config/outputs'
import { PRODUCER_CONFIG_MAP, ProducerName } from '../ingestion/heatmaps/config/producers'
import { HeatmapsConsumer } from '../ingestion/heatmaps/heatmaps-consumer'
import { KafkaProducerRegistry, resolveIngestionOutputs } from '../ingestion/outputs'
import { PluginServerService, RedisPool } from '../types'
import { ServerCommands } from '../utils/commands'
import { PostgresRouter } from '../utils/db/postgres'
import { createRedisPoolFromConfig } from '../utils/db/redis'
import { logger } from '../utils/logger'
import { PubSub } from '../utils/pubsub'
import { TeamManager } from '../utils/team-manager'
import { BaseServerConfig, CleanupResources, NodeServer, ServerLifecycle } from './base-server'

/**
 * Complete config type for a heatmaps ingestion deployment.
 *
 * This is the union of:
 * - BaseServerConfig: HTTP server, profiling, pod termination lifecycle
 * - HeatmapsConsumerConfig: heatmaps pipeline topics
 * - Infrastructure configs: Kafka broker, Postgres, Redis, consumer tuning
 * - Remaining CommonConfig picks: server mode, observability
 */
export type IngestionHeatmapsServerConfig = BaseServerConfig &
    HeatmapsConsumerConfig &
    KafkaBrokerConfig &
    DatabaseConnectionConfig &
    RedisConnectionsConfig &
    KafkaConsumerBaseConfig &
    Pick<
        CommonConfig,
        | 'LOG_LEVEL'
        | 'PLUGIN_SERVER_MODE'
        | 'CLOUD_DEPLOYMENT'
        | 'HEALTHCHECK_MAX_STALE_SECONDS'
        | 'KAFKA_HEALTHCHECK_SECONDS'
    >

export class IngestionHeatmapsServer implements NodeServer {
    readonly lifecycle: ServerLifecycle
    private config: IngestionHeatmapsServerConfig

    private postgres?: PostgresRouter
    private producerRegistry?: KafkaProducerRegistry<ProducerName>
    private redisPool?: RedisPool
    private pubsub?: PubSub

    constructor(config: Partial<IngestionHeatmapsServerConfig> = {}) {
        this.config = { ...defaultConfig, ...config }
        this.lifecycle = new ServerLifecycle(this.config)
    }

    async start(): Promise<void> {
        return this.lifecycle.start(
            () => this.startServices(),
            () => this.getCleanupResources()
        )
    }

    async stop(error?: Error): Promise<void> {
        return this.lifecycle.stop(() => this.getCleanupResources(), error)
    }

    private async startServices(): Promise<void> {
        initializePrometheusLabels(this.config.INGESTION_PIPELINE ?? 'heatmaps', this.config.INGESTION_LANE ?? 'main')

        // 1. Shared infrastructure
        logger.info('ℹ️', 'Connecting to shared infrastructure...')

        this.postgres = new PostgresRouter(this.config)
        logger.info('👍', 'Postgres Router ready')

        logger.info('🤔', 'Connecting to Kafka...')
        this.producerRegistry = new KafkaProducerRegistry(this.config.KAFKA_CLIENT_RACK, PRODUCER_CONFIG_MAP)
        const outputs = await resolveIngestionOutputs(this.producerRegistry, HEATMAPS_OUTPUT_DEFINITIONS)
        logger.info('👍', 'Kafka ready')

        logger.info('🤔', 'Connecting to ingestion Redis...')
        this.redisPool = createRedisPoolFromConfig({
            connection: createIngestionRedisConnectionConfig(this.config),
            poolMinSize: this.config.REDIS_POOL_MIN_SIZE,
            poolMaxSize: this.config.REDIS_POOL_MAX_SIZE,
        })
        logger.info('👍', 'Ingestion Redis ready')

        this.pubsub = new PubSub(this.redisPool)
        await this.pubsub.start()

        const teamManager = new TeamManager(this.postgres)

        // 2. Heatmaps consumer
        const serviceLoaders: (() => Promise<PluginServerService>)[] = []

        serviceLoaders.push(async () => {
            const consumer = new HeatmapsConsumer(
                {
                    groupId: this.config.HEATMAPS_CONSUMER_GROUP_ID,
                    topic: this.config.HEATMAPS_CONSUMER_CONSUME_TOPIC,
                    pipeline: this.config.INGESTION_PIPELINE ?? 'heatmaps',
                },
                {
                    outputs,
                    teamManager,
                }
            )
            await consumer.start()
            return consumer.service
        })

        serviceLoaders.push(() => {
            const serverCommands = new ServerCommands(this.pubsub!)
            this.lifecycle.expressApp.use('/', serverCommands.router())
            return Promise.resolve(serverCommands.service)
        })

        const readyServices = await Promise.all(serviceLoaders.map((loader) => loader()))
        this.lifecycle.services.push(...readyServices)
    }

    private getCleanupResources(): CleanupResources {
        return {
            kafkaProducers: [],
            redisPools: [this.redisPool].filter(Boolean) as RedisPool[],
            postgres: this.postgres,
            pubsub: this.pubsub,
            additionalCleanup: async () => {
                await this.producerRegistry?.disconnectAll()
            },
        }
    }
}
