import { actions, afterMount, connect, kea, listeners, path, reducers, selectors } from 'kea'
import { loaders } from 'kea-loaders'

import { teamLogic } from 'scenes/teamLogic'

import { Breadcrumb } from '~/types'

import { ciMonitoringReposList, ciMonitoringReposHealthRetrieve, ciMonitoringTestsList } from '../generated/api'
import type { CIHealthApi, RepoApi, TestCaseApi } from '../generated/api.schemas'
import type { ciMonitoringDashboardSceneLogicType } from './ciMonitoringDashboardSceneLogicType'

export type TestTab = 'needs_attention' | 'all' | 'quarantined'

export const ciMonitoringDashboardSceneLogic = kea<ciMonitoringDashboardSceneLogicType>([
    path(['products', 'ci_monitoring', 'frontend', 'scenes', 'ciMonitoringDashboardSceneLogic']),

    connect(() => ({
        values: [teamLogic, ['currentProjectId']],
    })),

    actions({
        setActiveTab: (tab: TestTab) => ({ tab }),
    }),

    reducers({
        activeTab: [
            'needs_attention' as TestTab,
            {
                setActiveTab: (_, { tab }) => tab,
            },
        ],
    }),

    loaders(({ values }) => ({
        repo: [
            null as RepoApi | null,
            {
                loadRepo: async () => {
                    const response = await ciMonitoringReposList(String(values.currentProjectId))
                    return response.results[0] || null
                },
            },
        ],
        health: [
            null as CIHealthApi | null,
            {
                loadHealth: async () => {
                    const repo = values.repo
                    if (!repo) {
                        return null
                    }
                    return await ciMonitoringReposHealthRetrieve(String(values.currentProjectId), repo.id)
                },
            },
        ],
        tests: [
            [] as TestCaseApi[],
            {
                loadTests: async () => {
                    const params = values.activeTab === 'needs_attention' ? { min_flake_score: 0.01 } : {}
                    const response = await ciMonitoringTestsList(String(values.currentProjectId), params)
                    const results = response.results
                    if (values.activeTab === 'quarantined') {
                        return results.filter((t) => t.quarantine !== null)
                    }
                    return results
                },
            },
        ],
    })),

    selectors({
        streak: [(s) => [s.health], (health): CIHealthApi['streak'] | null => health?.streak || null],
        breadcrumbs: [
            () => [],
            (): Breadcrumb[] => [
                {
                    key: 'ci_monitoring',
                    name: 'CI monitoring',
                    path: '/ci_monitoring',
                },
            ],
        ],
    }),

    listeners(({ actions }) => ({
        setActiveTab: () => {
            actions.loadTests()
        },
        loadRepoSuccess: () => {
            actions.loadHealth()
        },
    })),

    afterMount(({ actions }) => {
        actions.loadRepo()
        actions.loadTests()
    }),
])
