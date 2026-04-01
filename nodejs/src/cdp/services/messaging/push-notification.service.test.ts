import { HOG_EXAMPLES, HOG_FILTERS_EXAMPLES, HOG_INPUTS_EXAMPLES } from '~/cdp/_tests/examples'
import { createExampleInvocation, createHogFunction } from '~/cdp/_tests/fixtures'
import { CyclotronJobInvocationHogFunction } from '~/cdp/types'
import { EncryptedFields } from '~/cdp/utils/encryption-utils'

import { IntegrationManagerService } from '../managers/integration-manager.service'
import { PushNotificationFetchUtils, PushNotificationService } from './push-notification.service'

const encryptedFields = new EncryptedFields('01234567890123456789012345678901')

const createSendPushNotificationInvocation = (
    personProperties?: Record<string, any>
): CyclotronJobInvocationHogFunction => {
    const hogFunction = createHogFunction({
        name: 'Test FCM function',
        ...HOG_EXAMPLES.simple_fetch,
        ...HOG_INPUTS_EXAMPLES.simple_fetch,
        ...HOG_FILTERS_EXAMPLES.no_filters,
        inputs_schema: [
            {
                type: 'push_subscription',
                platform: 'android',
                key: 'device_token',
                label: 'Device Token',
            },
        ],
    })

    const invocation = createExampleInvocation(hogFunction)

    invocation.queueParameters = {
        type: 'sendPushNotification',
        integrationId: 1,
        distinctId: 'test-distinct-id',
        payload: {
            title: 'Test notification',
            body: 'Hello from PostHog',
        },
    } as any

    invocation.state.vmState = { stack: [] } as any

    if (personProperties) {
        invocation.state.globals.person = {
            ...(invocation.state.globals.person ?? { id: 'person-1', name: 'Test', url: '' }),
            properties: personProperties,
        }
    }

    return invocation
}

describe('PushNotificationService', () => {
    let service: PushNotificationService
    let integrationManager: IntegrationManagerService
    let fetchUtils: PushNotificationFetchUtils

    const mockTrackedFetch = jest.fn()

    const firebaseIntegration = {
        id: 1,
        team_id: 1,
        kind: 'firebase' as const,
        config: { project_id: 'test-project' },
        sensitive_config: { access_token: 'test-access-token' },
    }

    beforeEach(() => {
        integrationManager = {
            get: jest.fn().mockResolvedValue(firebaseIntegration),
        } as any

        fetchUtils = {
            trackedFetch: mockTrackedFetch,
            maxFetchTimeoutMs: 10000,
        }

        service = new PushNotificationService(integrationManager, encryptedFields, fetchUtils)
    })

    afterEach(() => {
        jest.restoreAllMocks()
    })

    describe('executeSendPushNotification', () => {
        it('throws when queue parameters type is not sendPushNotification', async () => {
            const invocation = createSendPushNotificationInvocation({
                '$device_push_subscription_test-project': encryptedFields.encrypt('device-token-123'),
            })
            invocation.queueParameters = { type: 'fetch', url: 'http://example.com', method: 'POST' } as any

            await expect(service.executeSendPushNotification(invocation)).rejects.toThrow('Bad invocation')
            expect(mockTrackedFetch).not.toHaveBeenCalled()
        })

        it('calls trackedFetch with url and fetchParams', async () => {
            const invocation = createSendPushNotificationInvocation({
                '$device_push_subscription_test-project': encryptedFields.encrypt('device-token-123'),
            })
            mockTrackedFetch.mockResolvedValue({
                fetchError: null,
                fetchResponse: {
                    status: 200,
                    text: () => Promise.resolve('{}'),
                    dump: () => Promise.resolve(),
                },
                fetchDuration: 10,
            })

            await service.executeSendPushNotification(invocation)

            expect(mockTrackedFetch).toHaveBeenCalledWith({
                url: 'https://fcm.googleapis.com/v1/projects/test-project/messages:send',
                fetchParams: expect.objectContaining({ method: 'POST' }),
                templateId: 'unknown',
            })
        })

        it('returns result with metric push_sent on success', async () => {
            const invocation = createSendPushNotificationInvocation({
                '$device_push_subscription_test-project': encryptedFields.encrypt('device-token-123'),
            })
            mockTrackedFetch.mockResolvedValue({
                fetchError: null,
                fetchResponse: {
                    status: 200,
                    text: () => Promise.resolve('{}'),
                    dump: () => Promise.resolve(),
                },
                fetchDuration: 10,
            })

            const result = await service.executeSendPushNotification(invocation)

            expect(result.metrics).toContainEqual(
                expect.objectContaining({
                    metric_name: 'push_sent',
                    count: 1,
                })
            )
            expect(result.finished).toBe(true)
        })

        it('logs warning when no device token found', async () => {
            const invocation = createSendPushNotificationInvocation({})

            const result = await service.executeSendPushNotification(invocation)

            expect(result.logs.map((log) => log.message)).toContainEqual(
                expect.stringContaining('No active FCM device token found')
            )
        })

        it('does not match tokens for a different app identifier', async () => {
            const invocation = createSendPushNotificationInvocation({
                '$device_push_subscription_other-project': encryptedFields.encrypt('other-token'),
            })

            const result = await service.executeSendPushNotification(invocation)

            expect(result.logs.map((log) => log.message)).toContainEqual(
                expect.stringContaining('No active FCM device token found')
            )
            expect(mockTrackedFetch).not.toHaveBeenCalled()
        })

        it('sets error when push fails', async () => {
            const invocation = createSendPushNotificationInvocation({
                '$device_push_subscription_test-project': encryptedFields.encrypt('device-token-123'),
            })
            mockTrackedFetch.mockResolvedValue({
                fetchError: null,
                fetchResponse: {
                    status: 500,
                    text: () => Promise.resolve('{}'),
                    dump: () => Promise.resolve(),
                },
                fetchDuration: 10,
            })

            const result = await service.executeSendPushNotification(invocation)

            expect(result.error).toBeTruthy()
        })

        it('returns error when integration not found', async () => {
            const invocation = createSendPushNotificationInvocation({
                '$device_push_subscription_test-project': encryptedFields.encrypt('device-token-123'),
            })
            ;(integrationManager.get as jest.Mock).mockResolvedValue(undefined)

            const result = await service.executeSendPushNotification(invocation)

            expect(result.error).toBeTruthy()
            expect(result.logs.map((log) => log.message)).toContain('Push notification integration not found')
        })

        it('handles missing person properties gracefully', async () => {
            const invocation = createSendPushNotificationInvocation()

            const result = await service.executeSendPushNotification(invocation)

            expect(result.logs.map((log) => log.message)).toContainEqual(
                expect.stringContaining('No active FCM device token found')
            )
        })
    })
})
