import { Counter } from 'prom-client'

import { instrumented } from '~/common/tracing/tracing-utils'
import { PluginsServerConfig } from '~/types'

import { logger } from '../../utils/logger'
import { CyclotronJobInvocation, CyclotronJobInvocationHogFunction, CyclotronJobInvocationResult } from '../types'
import { createInvocationResult } from '../utils/invocation-utils'
import { CdpConsumerBaseDeps } from './cdp-base.consumer'
import { CdpCyclotronWorker } from './cdp-cyclotron-worker.consumer'

const emailWorkerProcessed = new Counter({
    name: 'cdp_email_worker_processed_total',
    help: 'Total emails processed by the email worker',
    labelNames: ['status'],
})

export class CdpCyclotronWorkerEmail extends CdpCyclotronWorker {
    protected name = 'CdpCyclotronWorkerEmail'

    constructor(config: PluginsServerConfig, deps: CdpConsumerBaseDeps) {
        super(config, deps, 'email')
    }

    @instrumented('cdpConsumer.handleEachBatch.executeEmailInvocations')
    public async processInvocations(invocations: CyclotronJobInvocation[]): Promise<CyclotronJobInvocationResult[]> {
        const results: CyclotronJobInvocationResult[] = []

        for (const invocation of invocations) {
            try {
                if (invocation.queueParameters?.type !== 'email') {
                    logger.warn('Non-email job found in email queue', { id: invocation.id })
                    results.push(
                        createInvocationResult(
                            invocation,
                            {},
                            { finished: true, error: 'Non-email job in email queue' }
                        )
                    )
                    emailWorkerProcessed.inc({ status: 'invalid' })
                    continue
                }

                const result = await this.emailService.executeSendEmail(invocation as CyclotronJobInvocationHogFunction)
                results.push(result)
                emailWorkerProcessed.inc({ status: result.error ? 'error' : 'sent' })
            } catch (error) {
                logger.error('Email worker error', { id: invocation.id, error: String(error) })
                results.push(createInvocationResult(invocation, {}, { finished: true, error: String(error) }))
                emailWorkerProcessed.inc({ status: 'error' })
            }
        }

        return results
    }
}
