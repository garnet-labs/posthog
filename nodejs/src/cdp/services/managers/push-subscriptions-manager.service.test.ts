import '~/tests/helpers/mocks/date.mock'

import { createHash, randomUUID } from 'crypto'

import { getFirstTeam, resetTestDatabase } from '~/tests/helpers/sql'
import { Hub, Team } from '~/types'
import { closeHub, createHub } from '~/utils/db/hub'
import { PostgresUse } from '~/utils/db/postgres'

import { createHogFunction } from '../../_tests/fixtures'
import { HogFunctionType } from '../../types'
import { PushSubscriptionInputToLoad, PushSubscriptionsManagerService } from './push-subscriptions-manager.service'

describe('PushSubscriptionsManagerService', () => {
    describe('loadPushSubscriptions', () => {
        let hub: Hub
        let team: Team
        let manager: PushSubscriptionsManagerService
        let hogFunction: HogFunctionType
        let fcmIntegrationId: number
        let apnsIntegrationId: number

        const insertIntegration = async (
            teamId: number,
            kind: 'firebase' | 'apns',
            config: Record<string, any> = {}
        ): Promise<number> => {
            const result = await hub.postgres.query<{ id: number }>(
                PostgresUse.COMMON_WRITE,
                `INSERT INTO posthog_integration (team_id, kind, config, sensitive_config, created_at, created_by_id, errors)
                 VALUES ($1, $2, $3, '{}'::jsonb, NOW(), NULL, '')
                 RETURNING id`,
                [teamId, kind, JSON.stringify(config)],
                'insertIntegration'
            )
            return result.rows[0].id
        }

        const insertPushSubscription = async (
            teamId: number,
            distinctId: string,
            token: string,
            platform: 'android' | 'ios',
            integrationId: number,
            isActive: boolean = true
        ): Promise<void> => {
            const id = randomUUID()
            const encryptedToken = hub.encryptedFields.encrypt(token)
            const tokenHash = createHash('sha256').update(token, 'utf-8').digest('hex')

            await hub.postgres.query(
                PostgresUse.COMMON_WRITE,
                `INSERT INTO workflows_pushsubscription
                 (id, team_id, distinct_id, token, token_hash, platform, integration_id, is_active, created_at, updated_at)
                 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                 RETURNING *`,
                [id, teamId, distinctId, encryptedToken, tokenHash, platform, integrationId, isActive],
                'insertPushSubscription'
            )
        }

        const insertPersonDistinctId = async (teamId: number, personId: number, distinctId: string): Promise<void> => {
            await hub.postgres.query(
                PostgresUse.PERSONS_WRITE,
                `INSERT INTO posthog_persondistinctid (distinct_id, person_id, team_id, version)
                 VALUES ($1, $2, $3, 0)
                 ON CONFLICT DO NOTHING`,
                [distinctId, personId, teamId],
                'insertPersonDistinctId'
            )
        }

        const insertPerson = async (teamId: number): Promise<number> => {
            const personUuid = randomUUID()
            const result = await hub.postgres.query<{ id: number }>(
                PostgresUse.PERSONS_WRITE,
                `INSERT INTO posthog_person (uuid, team_id, created_at, properties, properties_last_updated_at, properties_last_operation, is_identified, version)
                 VALUES ($1, $2, NOW(), '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, true, 0)
                 RETURNING id`,
                [personUuid, teamId],
                'insertPerson'
            )
            return result.rows[0].id
        }

        beforeEach(async () => {
            await resetTestDatabase()
            hub = await createHub()
            team = await getFirstTeam(hub.postgres)
            manager = new PushSubscriptionsManagerService(hub.postgres, hub.encryptedFields)
            hogFunction = createHogFunction({
                id: 'hog-function-1',
                team_id: team.id,
                name: 'Hog Function 1',
                enabled: true,
                type: 'destination',
                inputs: {},
                inputs_schema: [],
            })
            fcmIntegrationId = await insertIntegration(team.id, 'firebase', { project_id: 'test-project' })
            apnsIntegrationId = await insertIntegration(team.id, 'apns', {
                bundle_id: 'com.example.app',
                team_id: 'APPLE_TEAM',
                key_id: 'KEY123',
            })
        })

        afterEach(async () => {
            if (hub) {
                await closeHub(hub)
            }
        })

        it('returns empty object when no inputs to load', async () => {
            const result = await manager.loadPushSubscriptions(hogFunction, {})
            expect(result).toEqual({})
        })

        it('resolves distinct_id to token for active subscription scoped by integration', async () => {
            const distinctId = 'user-123'
            const matchingToken = 'fcm-token-abc123'
            const nonMatchingToken = 'fcm-token-xyz789'
            const otherIntegrationId = await insertIntegration(team.id, 'firebase', { project_id: 'other-project' })
            await insertPushSubscription(team.id, distinctId, matchingToken, 'android', fcmIntegrationId)
            await insertPushSubscription(team.id, distinctId, nonMatchingToken, 'android', otherIntegrationId)

            const inputsToLoad: Record<string, PushSubscriptionInputToLoad> = {
                push_subscription: {
                    distinctId,
                    integrationId: fcmIntegrationId,
                },
            }
            const result = await manager.loadPushSubscriptions(hogFunction, inputsToLoad)
            expect(result).toEqual({
                push_subscription: { value: matchingToken },
            })
            expect(result.push_subscription.value).not.toBe(nonMatchingToken)
        })

        it('deactivates duplicate subscriptions with reason "duplicate" when multiple match', async () => {
            const distinctId = 'user-123'
            const token1 = 'fcm-token-first'
            const token2 = 'fcm-token-second'
            const token3 = 'fcm-token-third'
            await insertPushSubscription(team.id, distinctId, token1, 'android', fcmIntegrationId)
            await insertPushSubscription(team.id, distinctId, token2, 'android', fcmIntegrationId)
            await insertPushSubscription(team.id, distinctId, token3, 'android', fcmIntegrationId)

            const deactivateSpy = jest.spyOn(manager, 'deactivateByIds').mockResolvedValue(undefined)

            const inputsToLoad: Record<string, PushSubscriptionInputToLoad> = {
                push_subscription: {
                    distinctId,
                    integrationId: fcmIntegrationId,
                },
            }
            const result = await manager.loadPushSubscriptions(hogFunction, inputsToLoad)

            expect(result.push_subscription.value).toBeTruthy()
            expect([token1, token2, token3]).toContain(result.push_subscription.value)
            expect(deactivateSpy).toHaveBeenCalledTimes(1)
            expect(deactivateSpy).toHaveBeenCalledWith(expect.any(Array), 'duplicate', team.id)
            const deactivatedIds = deactivateSpy.mock.calls[0][0] as string[]
            expect(deactivatedIds).toHaveLength(2)
        })

        it('returns null for inactive subscription', async () => {
            const distinctId = 'user-123'
            const token = 'fcm-token-abc123'
            await insertPushSubscription(team.id, distinctId, token, 'android', fcmIntegrationId, false)

            const inputsToLoad: Record<string, PushSubscriptionInputToLoad> = {
                push_subscription: {
                    distinctId,
                    integrationId: fcmIntegrationId,
                },
            }
            const result = await manager.loadPushSubscriptions(hogFunction, inputsToLoad)
            expect(result).toEqual({
                push_subscription: { value: null },
            })
        })

        it('returns null for subscription from different team', async () => {
            const distinctId = 'user-123'
            const token = 'fcm-token-abc123'
            // Insert subscription for the real team
            await insertPushSubscription(team.id, distinctId, token, 'android', fcmIntegrationId)

            // But query with a hogFunction that belongs to a different team
            const otherTeamHogFunction = createHogFunction({
                ...hogFunction,
                team_id: 999,
            })

            const inputsToLoad: Record<string, PushSubscriptionInputToLoad> = {
                push_subscription: {
                    distinctId,
                    integrationId: fcmIntegrationId,
                },
            }
            const result = await manager.loadPushSubscriptions(otherTeamHogFunction, inputsToLoad)
            expect(result).toEqual({
                push_subscription: { value: null },
            })
        })

        it('filters by platform when specified', async () => {
            const distinctId = 'user-123'
            const androidToken = 'fcm-token-android'
            const iosToken = 'apns-token-ios'
            await insertPushSubscription(team.id, distinctId, androidToken, 'android', fcmIntegrationId)
            await insertPushSubscription(team.id, distinctId, iosToken, 'ios', apnsIntegrationId)

            const inputsToLoad: Record<string, PushSubscriptionInputToLoad> = {
                push_subscription: {
                    distinctId,
                    integrationId: fcmIntegrationId,
                },
            }
            const result = await manager.loadPushSubscriptions(hogFunction, inputsToLoad)
            expect(result).toEqual({
                push_subscription: { value: androidToken },
            })
        })

        it('falls back to related distinct_ids for same person and updates distinct_id', async () => {
            const originalDistinctId = 'user-original'
            const newDistinctId = 'user-new'
            const token = 'fcm-token-abc123'

            const personId = await insertPerson(team.id)
            await insertPersonDistinctId(team.id, personId, originalDistinctId)
            await insertPersonDistinctId(team.id, personId, newDistinctId)
            await insertPushSubscription(team.id, originalDistinctId, token, 'android', fcmIntegrationId)

            const inputsToLoad: Record<string, PushSubscriptionInputToLoad> = {
                push_subscription: {
                    distinctId: newDistinctId,
                    integrationId: fcmIntegrationId,
                },
            }
            const result = await manager.loadPushSubscriptions(hogFunction, inputsToLoad)
            expect(result).toEqual({
                push_subscription: { value: token },
            })

            const tokenHash = createHash('sha256').update(token, 'utf-8').digest('hex')
            const updatedSub = await hub.postgres.query(
                PostgresUse.COMMON_READ,
                `SELECT distinct_id FROM workflows_pushsubscription WHERE team_id = $1 AND token_hash = $2 LIMIT 1`,
                [team.id, tokenHash],
                'checkUpdatedDistinctId'
            )
            expect(updatedSub.rows[0]?.distinct_id).toBe(newDistinctId)
        })

        it('deactivates duplicate subscriptions from person-merge path', async () => {
            const distinctIdA = 'user-a'
            const distinctIdB = 'user-b'
            const tokenB1 = 'fcm-token-b1'
            const tokenB2 = 'fcm-token-b2'

            const personId = await insertPerson(team.id)
            await insertPersonDistinctId(team.id, personId, distinctIdA)
            await insertPersonDistinctId(team.id, personId, distinctIdB)
            await insertPushSubscription(team.id, distinctIdB, tokenB1, 'android', fcmIntegrationId)
            await insertPushSubscription(team.id, distinctIdB, tokenB2, 'android', fcmIntegrationId)

            const deactivateSpy = jest.spyOn(manager, 'deactivateByIds').mockResolvedValue(undefined)

            const inputsToLoad: Record<string, PushSubscriptionInputToLoad> = {
                push_subscription: {
                    distinctId: distinctIdA,
                    integrationId: fcmIntegrationId,
                },
            }
            const result = await manager.loadPushSubscriptions(hogFunction, inputsToLoad)

            expect([tokenB1, tokenB2]).toContain(result.push_subscription.value)
            expect(deactivateSpy).toHaveBeenCalledTimes(1)
            const deactivatedIds = deactivateSpy.mock.calls[0][0] as string[]
            expect(deactivatedIds).toHaveLength(1)
        })

        it('handles multiple push subscription inputs for FCM and APNS', async () => {
            const distinctId1 = 'user-1'
            const distinctId2 = 'user-2'
            const fcmToken = 'fcm-token-1'
            const apnsToken = 'apns-token-1'
            await insertPushSubscription(team.id, distinctId1, fcmToken, 'android', fcmIntegrationId)
            await insertPushSubscription(team.id, distinctId2, apnsToken, 'ios', apnsIntegrationId)

            const inputsToLoad: Record<string, PushSubscriptionInputToLoad> = {
                android_token: {
                    distinctId: distinctId1,
                    integrationId: fcmIntegrationId,
                },
                ios_token: {
                    distinctId: distinctId2,
                    integrationId: apnsIntegrationId,
                },
            }
            const result = await manager.loadPushSubscriptions(hogFunction, inputsToLoad)
            expect(result).toEqual({
                android_token: { value: fcmToken },
                ios_token: { value: apnsToken },
            })
        })

        it('scopes subscriptions by integration_id so FCM and APNS do not cross-match', async () => {
            const distinctId = 'user-123'
            const fcmToken = 'fcm-token-abc123'
            const apnsToken = 'apns-token-xyz789'

            await insertPushSubscription(team.id, distinctId, fcmToken, 'android', fcmIntegrationId)
            await insertPushSubscription(team.id, distinctId, apnsToken, 'ios', apnsIntegrationId)

            const fcmResult = await manager.loadPushSubscriptions(hogFunction, {
                push_subscription: {
                    distinctId,
                    integrationId: fcmIntegrationId,
                },
            })
            expect(fcmResult).toEqual({
                push_subscription: { value: fcmToken },
            })

            manager.clear()

            const apnsResult = await manager.loadPushSubscriptions(hogFunction, {
                push_subscription: {
                    distinctId,
                    integrationId: apnsIntegrationId,
                },
            })
            expect(apnsResult).toEqual({
                push_subscription: { value: apnsToken },
            })
        })

        it('returns null when subscription not found', async () => {
            const inputsToLoad: Record<string, PushSubscriptionInputToLoad> = {
                push_subscription: {
                    distinctId: 'non-existent-user',
                    integrationId: fcmIntegrationId,
                },
            }
            const result = await manager.loadPushSubscriptions(hogFunction, inputsToLoad)
            expect(result).toEqual({
                push_subscription: { value: null },
            })
        })
    })
})
