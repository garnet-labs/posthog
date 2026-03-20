import { Counter } from 'prom-client'

import { instrumented } from '~/common/tracing/tracing-utils'
import { FetchOptions, FetchResponse } from '~/utils/request'

import {
    CyclotronInvocationQueueParametersSendPushNotificationType,
    PushNotificationPayloadType,
} from '../../../schema/cyclotron'
import { parseJSON } from '../../../utils/json-parse'
import { CyclotronJobInvocationHogFunction, CyclotronJobInvocationResult, IntegrationType } from '../../types'
import { createAddLogFunction } from '../../utils'
import { createInvocationResult } from '../../utils/invocation-utils'
import { IntegrationManagerService } from '../managers/integration-manager.service'
import { FcmErrorDetail, PushSubscriptionsManagerService } from '../managers/push-subscriptions-manager.service'

const pushNotificationSentCounter = new Counter({
    name: 'push_notification_sent_total',
    help: 'Total number of push notifications successfully sent',
    labelNames: ['platform'],
})

export type PushNotificationFetchUtils = {
    trackedFetch: (args: { url: string; fetchParams: FetchOptions; templateId: string }) => Promise<{
        fetchError: Error | null
        fetchResponse: FetchResponse | null
        fetchDuration: number
    }>
    maxFetchTimeoutMs: number
}

export class PushNotificationService {
    constructor(
        private integrationManager: IntegrationManagerService,
        private pushSubscriptionsManager: PushSubscriptionsManagerService,
        private fetchUtils: PushNotificationFetchUtils
    ) {}

    @instrumented('push-notification.executeSendPushNotification')
    async executeSendPushNotification(
        invocation: CyclotronJobInvocationHogFunction
    ): Promise<CyclotronJobInvocationResult<CyclotronJobInvocationHogFunction>> {
        if (invocation.queueParameters?.type !== 'sendPushNotification') {
            throw new Error('Bad invocation')
        }

        const params = invocation.queueParameters as CyclotronInvocationQueueParametersSendPushNotificationType
        const result = createInvocationResult<CyclotronJobInvocationHogFunction>(invocation, {}, { finished: true })
        const addLog = createAddLogFunction(result.logs)

        let success = false

        try {
            const integration = await this.integrationManager.get(params.integrationId)
            if (!integration || integration.team_id !== invocation.teamId) {
                throw new Error('Push notification integration not found')
            }

            if (integration.kind === 'firebase') {
                await this.executeFcm(result, params, integration)
            } else if (integration.kind === 'apple-push') {
                await this.executeApns(result, params, integration)
            } else {
                throw new Error(`Unsupported push integration kind: ${integration.kind}`)
            }

            success = true
        } catch (error) {
            addLog('error', error.message)
            result.error = error.message
        }

        result.invocation.state.vmState!.stack.push({ success })

        result.metrics.push({
            team_id: invocation.teamId,
            app_source_id: invocation.parentRunId ?? invocation.functionId,
            instance_id: invocation.state.actionId || invocation.id,
            metric_kind: 'other',
            metric_name: 'sendPushNotification' as const,
            count: 1,
        })

        return result
    }

    private async executeFcm(
        result: CyclotronJobInvocationResult<CyclotronJobInvocationHogFunction>,
        params: CyclotronInvocationQueueParametersSendPushNotificationType,
        integration: IntegrationType
    ): Promise<void> {
        const addLog = createAddLogFunction(result.logs)
        const payload = params.payload
        const teamId = result.invocation.teamId

        const projectId = integration.config.project_id
        const accessToken = integration.sensitive_config.access_token ?? integration.config.access_token
        if (!projectId || !accessToken) {
            throw new Error('Firebase integration is missing project_id or access_token')
        }

        // Look up device tokens for this distinct ID
        const subscriptions = await this.pushSubscriptionsManager.get({
            teamId,
            distinctId: params.distinctId,
            fcmProjectId: projectId,
            provider: 'fcm',
        })

        if (subscriptions.length === 0) {
            addLog('warn', `No active FCM device tokens found for distinct_id: ${params.distinctId}`)
            return
        }

        const url = `https://fcm.googleapis.com/v1/projects/${projectId}/messages:send`
        const templateId = result.invocation.hogFunction.template_id ?? 'unknown'
        let sentCount = 0

        for (const subscription of subscriptions) {
            const fcmMessage = this.buildFcmMessage(subscription.token, payload)

            const fetchParams: FetchOptions = {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(fcmMessage),
            }

            if (params.timeoutMs !== undefined) {
                fetchParams.timeoutMs = Math.min(params.timeoutMs, this.fetchUtils.maxFetchTimeoutMs)
            }

            const { fetchError, fetchResponse, fetchDuration } = await this.fetchUtils.trackedFetch({
                url,
                fetchParams,
                templateId,
            })

            result.invocation.state.timings.push({
                kind: 'async_function',
                duration_ms: fetchDuration,
            })

            let body: unknown = undefined
            try {
                body = await fetchResponse?.text()
                if (typeof body === 'string') {
                    try {
                        body = parseJSON(body)
                    } catch (_e) {
                        // Pass through
                    }
                }
            } catch (e) {
                addLog('error', `Failed to parse response body: ${e.message}`)
            }

            // Handle FCM token lifecycle
            const status = fetchResponse?.status
            let errorDetails: FcmErrorDetail[] | undefined
            if (status === 400 && body && typeof body === 'object') {
                const errorBody = body as Record<string, unknown>
                const error = errorBody?.error as { details?: FcmErrorDetail[] } | undefined
                errorDetails = error?.details
            }
            await this.pushSubscriptionsManager.updateTokenLifecycle(teamId, subscription.token, status, errorDetails)

            if (!fetchResponse || (status && status >= 400)) {
                const message = `Push notification to device ${subscription.id} failed with status ${status ?? '(none)'}.${fetchError ? ` Error: ${fetchError.message}.` : ''}`
                addLog('error', message)
                continue
            }

            sentCount++
        }

        if (sentCount === 0) {
            throw new Error(`Push notification failed for all ${subscriptions.length} device(s)`)
        }

        pushNotificationSentCounter.labels({ platform: 'android' }).inc(sentCount)
        addLog('info', `Push notification sent via FCM to ${sentCount}/${subscriptions.length} device(s)`)
    }

    private executeApns(
        _result: CyclotronJobInvocationResult<CyclotronJobInvocationHogFunction>,
        _params: CyclotronInvocationQueueParametersSendPushNotificationType,
        _integration: IntegrationType
    ): Promise<void> {
        // TODO: Implement APNS direct delivery (requires HTTP/2)
        throw new Error('Direct APNS delivery is not yet supported. Use FCM to deliver to iOS devices.')
    }

    private buildFcmMessage(token: string, payload: PushNotificationPayloadType): Record<string, unknown> {
        const notification: Record<string, string> = { title: payload.title }
        if (payload.body) {
            notification.body = payload.body
        }
        if (payload.image) {
            notification.image = payload.image
        }

        const message: Record<string, unknown> = {
            token,
            notification,
        }

        if (payload.data) {
            message.data = payload.data
        }

        // Android-specific config
        if (payload.android || payload.collapseKey || payload.ttlSeconds !== undefined) {
            const android: Record<string, unknown> = {}
            if (payload.collapseKey) {
                android.collapse_key = payload.collapseKey
            }
            if (payload.ttlSeconds !== undefined) {
                android.ttl = `${payload.ttlSeconds}s`
            }
            if (payload.android) {
                if (payload.android.priority) {
                    android.priority = payload.android.priority.toUpperCase()
                }
                const androidNotification: Record<string, string> = {}
                if (payload.android.channelId) {
                    androidNotification.channel_id = payload.android.channelId
                }
                if (payload.android.sound) {
                    androidNotification.sound = payload.android.sound
                }
                if (payload.android.tag) {
                    androidNotification.tag = payload.android.tag
                }
                if (payload.android.icon) {
                    androidNotification.icon = payload.android.icon
                }
                if (payload.android.color) {
                    androidNotification.color = payload.android.color
                }
                if (payload.android.clickAction) {
                    androidNotification.click_action = payload.android.clickAction
                }
                if (Object.keys(androidNotification).length > 0) {
                    android.notification = androidNotification
                }
            }
            message.android = android
        }

        // APNS overrides (for iOS devices via FCM)
        if (payload.apns) {
            const aps: Record<string, unknown> = {}
            if (payload.apns.sound) {
                aps.sound = payload.apns.sound
            }
            if (payload.apns.badge !== undefined) {
                aps.badge = payload.apns.badge
            }
            if (payload.apns.category) {
                aps.category = payload.apns.category
            }
            if (payload.apns.threadId) {
                aps['thread-id'] = payload.apns.threadId
            }
            if (payload.apns.interruptionLevel) {
                aps['interruption-level'] = payload.apns.interruptionLevel
            }
            if (payload.apns.relevanceScore !== undefined) {
                aps['relevance-score'] = payload.apns.relevanceScore
            }
            if (payload.apns.subtitle) {
                // Subtitle goes in the alert object
                notification.subtitle = payload.apns.subtitle
            }
            if (payload.apns.mutableContent) {
                aps['mutable-content'] = 1
            }
            if (payload.apns.targetContentId) {
                aps['target-content-id'] = payload.apns.targetContentId
            }

            message.apns = {
                payload: { aps },
            }

            // Set collapse ID via APNS header if collapseKey is set
            if (payload.collapseKey) {
                ;(message.apns as Record<string, unknown>).headers = {
                    'apns-collapse-id': payload.collapseKey,
                }
            }
            if (payload.ttlSeconds !== undefined) {
                const headers = ((message.apns as Record<string, unknown>).headers as Record<string, string>) ?? {}
                headers['apns-expiration'] = String(Math.floor(Date.now() / 1000) + payload.ttlSeconds)
                ;(message.apns as Record<string, unknown>).headers = headers
            }
        }

        return { message }
    }
}
