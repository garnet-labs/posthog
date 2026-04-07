import { Message } from 'node-rdkafka'

import { PromiseScheduler } from '~/utils/promise-scheduler'
import { TeamManager } from '~/utils/team-manager'

import { Team } from '../../types'
import { DlqOutput, IngestionWarningsOutput } from '../common/outputs'
import { createParseHeadersStep, createParseKafkaMessageStep, createResolveTeamStep } from '../event-preprocessing'
import { createCheckHeatmapOptInStep } from '../event-processing/check-heatmap-opt-in-step'
import { createDisablePersonProcessingStep } from '../event-processing/disable-person-processing-step'
import { createExtractHeatmapDataStep } from '../event-processing/extract-heatmap-data-step'
import { createNormalizeEventStep } from '../event-processing/normalize-event-step'
import { createPrepareEventStep } from '../event-processing/prepare-event-step'
import { createSkipEmitEventStep } from '../event-processing/skip-emit-event-step'
import { IngestionOutputs } from '../outputs/ingestion-outputs'
import { BatchPipelineUnwrapper } from '../pipelines/batch-pipeline-unwrapper'
import { newBatchPipelineBuilder } from '../pipelines/builders'
import { createBatch, createUnwrapper } from '../pipelines/helpers'
import { OkResultWithContext } from '../pipelines/pipeline.interface'
import { PipelineConfig } from '../pipelines/result-handling-pipeline'
import { HeatmapsOutput } from './outputs'

export interface HeatmapsPipelineInput {
    message: Message
}

export type HeatmapsPipelineOutput = void

export type HeatmapsPipelineOutputs = IngestionOutputs<HeatmapsOutput | IngestionWarningsOutput | DlqOutput>

export interface HeatmapsPipelineConfig {
    outputs: HeatmapsPipelineOutputs
    promiseScheduler: PromiseScheduler
    teamManager: TeamManager
}

/**
 * Lift the resolved team from the result value into the pipeline context, so that
 * downstream `teamAware` and `handleIngestionWarnings` blocks can access it.
 */
function addTeamToContext<T extends { team: Team }, C>(
    element: OkResultWithContext<T, C>
): OkResultWithContext<T, C & { team: Team }> {
    return {
        result: element.result,
        context: {
            ...element.context,
            team: element.result.value.team,
        },
    }
}

export function createHeatmapsPipeline(
    config: HeatmapsPipelineConfig
): BatchPipelineUnwrapper<HeatmapsPipelineInput, HeatmapsPipelineOutput, { message: Message }, never> {
    const { outputs, promiseScheduler, teamManager } = config

    const pipelineConfig: PipelineConfig<never> = {
        outputs,
        promiseScheduler,
    }

    const pipeline = newBatchPipelineBuilder<HeatmapsPipelineInput, { message: Message }>()
        .messageAware((b) =>
            b
                .sequentially((b) =>
                    b
                        .pipe(createParseHeadersStep())
                        .pipe(createParseKafkaMessageStep())
                        .pipe(createResolveTeamStep(teamManager))
                )
                .filterMap(addTeamToContext, (b) =>
                    b
                        .teamAware((b) =>
                            b.sequentially((b) =>
                                b
                                    .pipe(createCheckHeatmapOptInStep())
                                    // processPerson flag is required by normalizeEventStep
                                    .pipe(createDisablePersonProcessingStep())
                                    .pipe(createNormalizeEventStep())
                                    .pipe(createPrepareEventStep())
                                    .pipe(createExtractHeatmapDataStep(outputs))
                                    .pipe(createSkipEmitEventStep())
                            )
                        )
                        .handleIngestionWarnings(outputs)
                )
        )
        .handleResults(pipelineConfig)
        .handleSideEffects(promiseScheduler, { await: false })
        .gather()
        .build()

    return createUnwrapper(pipeline)
}

export async function runHeatmapsPipeline(
    pipeline: BatchPipelineUnwrapper<HeatmapsPipelineInput, HeatmapsPipelineOutput, { message: Message }, never>,
    messages: Message[]
): Promise<void> {
    if (messages.length === 0) {
        return
    }

    const batch = createBatch(messages.map((message) => ({ message })))
    pipeline.feed(batch)

    while ((await pipeline.next()) !== null) {
        // Drain all results
    }
}
