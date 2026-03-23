import { expectLogic } from 'kea-test-utils'

import { FEATURE_FLAGS } from 'lib/constants'
import { featureFlagLogic } from 'lib/logic/featureFlagLogic'
import { databaseTableListLogic } from 'scenes/data-management/database/databaseTableListLogic'
import { sceneLogic } from 'scenes/sceneLogic'
import { teamLogic } from 'scenes/teamLogic'

import { useMocks } from '~/mocks/jest'
import { initKeaTests } from '~/test/init'
import { QueryTabState } from '~/types'

import { queryDatabaseLogic } from './queryDatabaseLogic'

describe('queryDatabaseLogic', () => {
    let logic: ReturnType<typeof queryDatabaseLogic.build>
    let databaseLogic: ReturnType<typeof databaseTableListLogic.build>

    beforeEach(async () => {
        useMocks({
            get: {
                '/api/environments/:team_id/warehouse_saved_queries/': { results: [] },
                '/api/projects/:team_id/query_tab_state/user': null,
            },
        })

        initKeaTests()
        featureFlagLogic.mount()
        teamLogic.mount()
        sceneLogic.mount()
        databaseLogic = databaseTableListLogic()
        databaseLogic.mount()

        featureFlagLogic.actions.setFeatureFlags([FEATURE_FLAGS.DWH_POSTGRES_DIRECT_QUERY], {
            [FEATURE_FLAGS.DWH_POSTGRES_DIRECT_QUERY]: true,
        })

        await expectLogic(teamLogic).toFinishAllListeners()
    })

    afterEach(() => {
        logic?.unmount()
        databaseLogic?.unmount()
    })

    const setUnsavedQueryState = (): void => {
        const queryTabState = {
            id: 'state-id',
            state: {
                editorModelsStateKey: JSON.stringify([
                    {
                        name: 'Unsaved query 1',
                        query: 'SELECT 1',
                        path: 'query-1',
                    },
                ]),
            },
        } as QueryTabState

        logic.actions.loadQueryTabStateSuccess(queryTabState)
    }

    it('shows unsaved queries without a direct connection', async () => {
        logic = queryDatabaseLogic()
        logic.mount()

        databaseLogic.actions.loadDatabaseSuccess({ tables: {}, joins: [] })
        setUnsavedQueryState()

        await expectLogic(logic).toMatchValues({
            displayedTreeData: expect.arrayContaining([expect.objectContaining({ id: 'unsaved-folder' })]),
        })
    })

    it('hides unsaved queries when a direct connection is selected', async () => {
        logic = queryDatabaseLogic()
        logic.mount()

        databaseLogic.actions.loadDatabaseSuccess({ tables: {}, joins: [] })
        setUnsavedQueryState()
        databaseLogic.actions.setConnection('conn-123')

        await expectLogic(logic).toMatchValues({
            displayedTreeData: expect.not.arrayContaining([expect.objectContaining({ id: 'unsaved-folder' })]),
        })
    })
})
