import { HOG_EXAMPLES, HOG_FILTERS_EXAMPLES, HOG_INPUTS_EXAMPLES } from '~/cdp/_tests/examples'
import { createExampleInvocation, createHogFunction } from '~/cdp/_tests/fixtures'
import { CyclotronJobInvocationHogFunction } from '~/cdp/types'

import { IntegrationManagerService } from '../managers/integration-manager.service'
import { PushSubscriptionsManagerService } from '../managers/push-subscriptions-manager.service'
import { PushNotificationFetchUtils, PushNotificationService } from './push-notification.service'

const createSendPushNotificationInvocation = (token: string | null | undefined): CyclotronJobInvocationHogFunction => {
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

    const invocation = createExampleInvocation(hogFunction, {
        inputs: token !== undefined ? { device_token: token } : {},
    })

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

    return invocation
}

describe('PushNotificationService', () => {
    let service: PushNotificationService
    let integrationManager: IntegrationManagerService
    let pushSubscriptionsManager: PushSubscriptionsManagerService
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
        pushSubscriptionsManager = {
            get: jest.fn().mockResolvedValue([{ id: 'sub-1', token: 'device-token-123' }]),
            updateLastSuccessfullyUsedAtByToken: jest.fn().mockResolvedValue(undefined),
            deactivateByTokens: jest.fn().mockResolvedValue(undefined),
            updateFcmTokenLifecycle: jest.fn().mockResolvedValue(undefined),
            updateApnsTokenLifecycle: jest.fn().mockResolvedValue(undefined),
        } as any

        fetchUtils = {
            trackedFetch: mockTrackedFetch,
            maxFetchTimeoutMs: 10000,
        }

        service = new PushNotificationService(integrationManager, pushSubscriptionsManager, fetchUtils)
    })

    afterEach(() => {
        jest.restoreAllMocks()
    })

    describe('executeSendPushNotification', () => {
        it('throws when queue parameters type is not sendPushNotification', async () => {
            const invocation = createSendPushNotificationInvocation('token')
            invocation.queueParameters = { type: 'fetch', url: 'http://example.com', method: 'POST' } as any

            await expect(service.executeSendPushNotification(invocation)).rejects.toThrow('Bad invocation')
            expect(mockTrackedFetch).not.toHaveBeenCalled()
        })

        it('calls trackedFetch with url and fetchParams', async () => {
            const invocation = createSendPushNotificationInvocation('token')
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

        it('returns result with execResult and metric push_sent on success', async () => {
            const invocation = createSendPushNotificationInvocation('token')
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

        it('logs warning when no device tokens found', async () => {
            const invocation = createSendPushNotificationInvocation(null)
            ;(pushSubscriptionsManager.get as jest.Mock).mockResolvedValue([])

            const result = await service.executeSendPushNotification(invocation)

            expect(result.logs.map((log) => log.message)).toContainEqual(
                expect.stringContaining('No active FCM device tokens found')
            )
            expect(pushSubscriptionsManager.updateFcmTokenLifecycle).not.toHaveBeenCalled()
        })

        it('handles successful response (200) and calls updateFcmTokenLifecycle', async () => {
            const invocation = createSendPushNotificationInvocation('token')
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

            expect(pushSubscriptionsManager.updateFcmTokenLifecycle).toHaveBeenCalledWith(
                1,
                'device-token-123',
                200,
                undefined
            )
        })

        it('handles 404 response and calls updateFcmTokenLifecycle (deactivate)', async () => {
            const invocation = createSendPushNotificationInvocation('token')
            mockTrackedFetch.mockResolvedValue({
                fetchError: null,
                fetchResponse: {
                    status: 404,
                    text: () => Promise.resolve('{}'),
                    dump: () => Promise.resolve(),
                },
                fetchDuration: 10,
            })

            const result = await service.executeSendPushNotification(invocation)

            expect(pushSubscriptionsManager.updateFcmTokenLifecycle).toHaveBeenCalledWith(
                1,
                'device-token-123',
                404,
                undefined
            )
            // All devices failed, so error should be thrown and caught
            expect(result.logs.map((log) => log.message)).toContainEqual(expect.stringContaining('failed for all'))
        })

        it('handles 400 with INVALID_ARGUMENT and passes error details to updateFcmTokenLifecycle', async () => {
            const responseBody = {
                error: {
                    code: 400,
                    details: [
                        {
                            '@type': 'type.googleapis.com/google.firebase.fcm.v1.FcmError',
                            errorCode: 'INVALID_ARGUMENT',
                        },
                    ],
                },
            }
            const invocation = createSendPushNotificationInvocation('token')
            mockTrackedFetch.mockResolvedValue({
                fetchError: null,
                fetchResponse: {
                    status: 400,
                    text: () => Promise.resolve(JSON.stringify(responseBody)),
                    dump: () => Promise.resolve(),
                },
                fetchDuration: 10,
            })

            await service.executeSendPushNotification(invocation)

            expect(pushSubscriptionsManager.updateFcmTokenLifecycle).toHaveBeenCalledWith(
                1,
                'device-token-123',
                400,
                responseBody.error.details
            )
        })

        it('handles 400 with empty error details and calls updateFcmTokenLifecycle', async () => {
            const responseBody = {
                error: {
                    code: 400,
                    details: [],
                },
            }
            const invocation = createSendPushNotificationInvocation('token')
            mockTrackedFetch.mockResolvedValue({
                fetchError: null,
                fetchResponse: {
                    status: 400,
                    text: () => Promise.resolve(JSON.stringify(responseBody)),
                    dump: () => Promise.resolve(),
                },
                fetchDuration: 10,
            })

            await service.executeSendPushNotification(invocation)

            expect(pushSubscriptionsManager.updateFcmTokenLifecycle).toHaveBeenCalledWith(
                1,
                'device-token-123',
                400,
                []
            )
        })

        it('handles other status codes and still calls updateFcmTokenLifecycle', async () => {
            const invocation = createSendPushNotificationInvocation('token')
            mockTrackedFetch.mockResolvedValue({
                fetchError: null,
                fetchResponse: {
                    status: 500,
                    text: () => Promise.resolve('{}'),
                    dump: () => Promise.resolve(),
                },
                fetchDuration: 10,
            })

            await service.executeSendPushNotification(invocation)

            expect(pushSubscriptionsManager.updateFcmTokenLifecycle).toHaveBeenCalledWith(
                1,
                'device-token-123',
                500,
                undefined
            )
        })

        it('sets error when all devices fail', async () => {
            const invocation = createSendPushNotificationInvocation('token')
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
            expect(result.logs.map((log) => log.message)).toContainEqual(expect.stringContaining('failed for all'))
        })

        it('returns error when integration not found', async () => {
            const invocation = createSendPushNotificationInvocation('token')
            ;(integrationManager.get as jest.Mock).mockResolvedValue(undefined)

            const result = await service.executeSendPushNotification(invocation)

            expect(result.error).toBeTruthy()
            expect(result.logs.map((log) => log.message)).toContain('Push notification integration not found')
        })
    })
})
