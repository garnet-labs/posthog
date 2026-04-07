import { Gauge } from 'prom-client'

import { HogTransformerService } from '../cdp/hog-transformations/hog-transformer.service'
import { CommonConfig } from '../common/config'
import {
    HealthCheckResult,
    HealthCheckResultError,
    HealthCheckResultOk,
    PluginServerService,
    RedisPool,
} from '../types'
import { PostgresRouter } from '../utils/db/postgres'
import { EventIngestionRestrictionManager } from '../utils/event-ingestion-restrictions'
import { EventSchemaEnforcementManager } from '../utils/event-schema-enforcement-manager'
import { PromiseScheduler } from '../utils/promise-scheduler'
import { TeamManager } from '../utils/team-manager'
import { GroupTypeManager } from '../worker/ingestion/group-type-manager'
import { BatchWritingGroupStore } from '../worker/ingestion/groups/batch-writing-group-store'
import { ClickhouseGroupRepository } from '../worker/ingestion/groups/repositories/clickhouse-group-repository'
import { GroupRepository } from '../worker/ingestion/groups/repositories/group-repository.interface'
import { BatchWritingPersonsStore } from '../worker/ingestion/persons/batch-writing-person-store'
import { PersonsStore } from '../worker/ingestion/persons/persons-store'
import { PersonRepository } from '../worker/ingestion/persons/repositories/person-repository'
import { JoinedIngestionPipelineConfig, JoinedIngestionPipelineDeps, createJoinedIngestionPipeline } from './analytics'
import {
    AiEventOutput,
    AsyncOutput,
    EventOutput,
    HeatmapsOutput,
    PersonDistinctIdsOutput,
    PersonsOutput,
} from './analytics/outputs'
import { CommonIngestionConsumer, IngestionPipelineLifecycle } from './common/common-ingestion-consumer'
import { EventFilterManager } from './common/event-filters'
import {
    AppMetricsOutput,
    DlqOutput,
    GroupsOutput,
    IngestionWarningsOutput,
    OverflowOutput,
    TophogOutput,
} from './common/outputs'
import { IngestionConsumerConfig } from './config'
import { CookielessManager } from './cookieless/cookieless-manager'
import { parseSplitAiEventsConfig } from './event-processing/split-ai-events-step'
import { IngestionOutputs } from './outputs/ingestion-outputs'
import { TopHog } from './tophog'
import { MainLaneOverflowRedirect } from './utils/overflow-redirect/main-lane-overflow-redirect'
import { OverflowLaneOverflowRedirect } from './utils/overflow-redirect/overflow-lane-overflow-redirect'
import { OverflowRedirectService } from './utils/overflow-redirect/overflow-redirect-service'
import { RedisOverflowRepository } from './utils/overflow-redirect/overflow-redis-repository'

export type IngestionConsumerFullConfig = IngestionConsumerConfig &
    Pick<CommonConfig, 'KAFKA_CLIENT_RACK' | 'CDP_HOG_WATCHER_SAMPLE_RATE'>

export interface IngestionConsumerDeps {
    postgres: PostgresRouter
    redisPool: RedisPool
    outputs: IngestionOutputs<
        | EventOutput
        | AiEventOutput
        | HeatmapsOutput
        | IngestionWarningsOutput
        | DlqOutput
        | OverflowOutput
        | AsyncOutput
        | GroupsOutput
        | PersonsOutput
        | PersonDistinctIdsOutput
        | AppMetricsOutput
        | TophogOutput
    >
    teamManager: TeamManager
    groupTypeManager: GroupTypeManager
    groupRepository: GroupRepository
    clickhouseGroupRepository: ClickhouseGroupRepository
    personRepository: PersonRepository
    cookielessManager: CookielessManager
    hogTransformer: HogTransformerService
}

export const latestOffsetTimestampGauge = new Gauge({
    name: 'latest_processed_timestamp_ms',
    help: 'Timestamp of the latest offset that has been committed.',
    labelNames: ['topic', 'partition', 'groupId'],
    aggregator: 'max',
})

export class IngestionConsumer {
    private consumer: CommonIngestionConsumer
    public hogTransformer: HogTransformerService
    private overflowRedirectService?: OverflowRedirectService
    private overflowLaneTTLRefreshService?: OverflowRedirectService
    private personsStore: PersonsStore
    public groupStore: BatchWritingGroupStore
    private eventFilterManager: EventFilterManager
    private eventIngestionRestrictionManager: EventIngestionRestrictionManager
    private eventSchemaEnforcementManager: EventSchemaEnforcementManager
    public readonly promiseScheduler: PromiseScheduler
    isStopping = false

    constructor(
        private config: IngestionConsumerFullConfig,
        private deps: IngestionConsumerDeps,
        overrides: Partial<
            Pick<
                IngestionConsumerConfig,
                | 'INGESTION_CONSUMER_GROUP_ID'
                | 'INGESTION_CONSUMER_CONSUME_TOPIC'
                | 'INGESTION_CONSUMER_OVERFLOW_TOPIC'
                | 'INGESTION_CONSUMER_DLQ_TOPIC'
            >
        > = {}
    ) {
        const groupId = overrides.INGESTION_CONSUMER_GROUP_ID ?? config.INGESTION_CONSUMER_GROUP_ID
        const topic = overrides.INGESTION_CONSUMER_CONSUME_TOPIC ?? config.INGESTION_CONSUMER_CONSUME_TOPIC

        const tokenDistinctIdsToDrop = config.DROP_EVENTS_BY_TOKEN_DISTINCT_ID.split(',').filter(Boolean)
        const tokenDistinctIdsToSkipPersons =
            config.SKIP_PERSONS_PROCESSING_BY_TOKEN_DISTINCT_ID.split(',').filter(Boolean)
        const tokenDistinctIdsToForceOverflow =
            config.INGESTION_FORCE_OVERFLOW_BY_TOKEN_DISTINCT_ID.split(',').filter(Boolean)
        this.eventIngestionRestrictionManager = new EventIngestionRestrictionManager(deps.redisPool, {
            pipeline: 'analytics',
            staticDropEventTokens: tokenDistinctIdsToDrop,
            staticSkipPersonTokens: tokenDistinctIdsToSkipPersons,
            staticForceOverflowTokens: tokenDistinctIdsToForceOverflow,
        })
        this.eventFilterManager = new EventFilterManager(deps.postgres)
        this.eventSchemaEnforcementManager = new EventSchemaEnforcementManager(deps.postgres)

        const overflowRedisRepository = new RedisOverflowRepository({
            redisPool: deps.redisPool,
            redisTTLSeconds: config.INGESTION_STATEFUL_OVERFLOW_REDIS_TTL_SECONDS,
        })

        const overflowEnabled =
            !!config.INGESTION_CONSUMER_OVERFLOW_TOPIC && config.INGESTION_CONSUMER_OVERFLOW_TOPIC !== topic

        if (overflowEnabled) {
            this.overflowRedirectService = new MainLaneOverflowRedirect({
                redisRepository: overflowRedisRepository,
                localCacheTTLSeconds: config.INGESTION_STATEFUL_OVERFLOW_LOCAL_CACHE_TTL_SECONDS,
                bucketCapacity: config.EVENT_OVERFLOW_BUCKET_CAPACITY,
                replenishRate: config.EVENT_OVERFLOW_BUCKET_REPLENISH_RATE,
                statefulEnabled: config.INGESTION_STATEFUL_OVERFLOW_ENABLED,
            })
        }

        if (config.INGESTION_LANE === 'overflow' && config.INGESTION_STATEFUL_OVERFLOW_ENABLED) {
            this.overflowLaneTTLRefreshService = new OverflowLaneOverflowRedirect({
                redisRepository: overflowRedisRepository,
            })
        }

        this.hogTransformer = deps.hogTransformer

        this.personsStore = new BatchWritingPersonsStore(deps.personRepository, deps.outputs, {
            dbWriteMode: config.PERSON_BATCH_WRITING_DB_WRITE_MODE,
            useBatchUpdates: config.PERSON_BATCH_WRITING_USE_BATCH_UPDATES,
            maxConcurrentUpdates: config.PERSON_BATCH_WRITING_MAX_CONCURRENT_UPDATES,
            maxOptimisticUpdateRetries: config.PERSON_BATCH_WRITING_MAX_OPTIMISTIC_UPDATE_RETRIES,
            optimisticUpdateRetryInterval: config.PERSON_BATCH_WRITING_OPTIMISTIC_UPDATE_RETRY_INTERVAL_MS,
            updateAllProperties: config.PERSON_PROPERTIES_UPDATE_ALL,
        })

        this.groupStore = new BatchWritingGroupStore(
            deps.outputs,
            deps.groupRepository,
            deps.clickhouseGroupRepository,
            {
                maxConcurrentUpdates: config.GROUP_BATCH_WRITING_MAX_CONCURRENT_UPDATES,
                maxOptimisticUpdateRetries: config.GROUP_BATCH_WRITING_MAX_OPTIMISTIC_UPDATE_RETRIES,
                optimisticUpdateRetryInterval: config.GROUP_BATCH_WRITING_OPTIMISTIC_UPDATE_RETRY_INTERVAL_MS,
            }
        )

        const topHog = new TopHog({
            outputs: deps.outputs,
            pipeline: config.INGESTION_PIPELINE ?? 'unknown',
            lane: config.INGESTION_LANE ?? 'unknown',
        })

        const joinedPipelineConfig: JoinedIngestionPipelineConfig = {
            eventSchemaEnforcementEnabled: config.EVENT_SCHEMA_ENFORCEMENT_ENABLED,
            overflowEnabled,
            preservePartitionLocality: config.INGESTION_OVERFLOW_PRESERVE_PARTITION_LOCALITY,
            personsPrefetchEnabled: config.PERSONS_PREFETCH_ENABLED,
            cdpHogWatcherSampleRate: config.CDP_HOG_WATCHER_SAMPLE_RATE,
            groupId,
            outputs: deps.outputs,
            splitAiEventsConfig: parseSplitAiEventsConfig(
                config.INGESTION_AI_EVENT_SPLITTING_ENABLED,
                config.INGESTION_AI_EVENT_SPLITTING_TEAMS,
                config.INGESTION_AI_EVENT_SPLITTING_STRIP_HEAVY
            ),
            perDistinctIdOptions: {
                SKIP_UPDATE_EVENT_AND_PROPERTIES_STEP: config.SKIP_UPDATE_EVENT_AND_PROPERTIES_STEP,
                PERSON_MERGE_MOVE_DISTINCT_ID_LIMIT: config.PERSON_MERGE_MOVE_DISTINCT_ID_LIMIT,
                PERSON_MERGE_ASYNC_ENABLED: config.PERSON_MERGE_ASYNC_ENABLED,
                PERSON_MERGE_SYNC_BATCH_SIZE: config.PERSON_MERGE_SYNC_BATCH_SIZE,
                PERSON_JSONB_SIZE_ESTIMATE_ENABLE: config.PERSON_JSONB_SIZE_ESTIMATE_ENABLE,
                PERSON_PROPERTIES_UPDATE_ALL: config.PERSON_PROPERTIES_UPDATE_ALL,
            },
        }
        const joinedPipelineDeps: JoinedIngestionPipelineDeps = {
            personsStore: this.personsStore,
            groupStore: this.groupStore,
            hogTransformer: this.hogTransformer,
            eventFilterManager: this.eventFilterManager,
            eventIngestionRestrictionManager: this.eventIngestionRestrictionManager,
            eventSchemaEnforcementManager: this.eventSchemaEnforcementManager,
            promiseScheduler: new PromiseScheduler(),
            overflowRedirectService: this.overflowRedirectService,
            overflowLaneTTLRefreshService: this.overflowLaneTTLRefreshService,
            teamManager: deps.teamManager,
            cookielessManager: deps.cookielessManager,
            groupTypeManager: deps.groupTypeManager,
            topHog,
        }
        const joinedPipeline = createJoinedIngestionPipeline(joinedPipelineConfig, joinedPipelineDeps)

        const lifecycle: IngestionPipelineLifecycle = {
            onStart: async () => {
                await this.hogTransformer.start()
                topHog.start()

                const topicFailures = await deps.outputs.checkTopics()
                if (topicFailures.length > 0) {
                    throw new Error(`Output topic verification failed for: ${topicFailures.join(', ')}`)
                }
            },
            onStop: async () => {
                await topHog.stop()
                await this.hogTransformer.stop()
            },
            healthcheck: async () => {
                if (process.env.INGESTION_OUTPUTS_PRODUCER_HEALTHCHECK === 'true') {
                    const failures = await deps.outputs.checkHealth()
                    if (failures.length > 0) {
                        return new HealthCheckResultError('Kafka producer(s) unhealthy', { failedProducers: failures })
                    }
                }
                return new HealthCheckResultOk()
            },
            getBackgroundWork: async () => {
                await this.hogTransformer.processInvocationResults()
            },
        }

        this.consumer = new CommonIngestionConsumer(config, joinedPipeline, lifecycle, {
            INGESTION_CONSUMER_GROUP_ID: groupId,
            INGESTION_CONSUMER_CONSUME_TOPIC: topic,
        })
        this.promiseScheduler = this.consumer.promiseScheduler
    }

    public get service(): PluginServerService {
        return this.consumer.service
    }

    public async start(): Promise<void> {
        return this.consumer.start()
    }

    public async stop(): Promise<void> {
        this.isStopping = true
        return this.consumer.stop()
    }

    public async isHealthy(): Promise<HealthCheckResult> {
        return this.consumer.isHealthy()
    }

    public async handleKafkaBatch(...args: Parameters<CommonIngestionConsumer['handleKafkaBatch']>) {
        return this.consumer.handleKafkaBatch(...args)
    }
}
