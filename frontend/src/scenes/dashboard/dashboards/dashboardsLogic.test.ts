import { MOCK_DEFAULT_USER } from 'lib/api.mock'

import { router } from 'kea-router'
import { expectLogic, truth } from 'kea-test-utils'

import {
    compareDashboardsListDefaultOrder,
    DashboardsTab,
    dashboardsLogic,
} from 'scenes/dashboard/dashboards/dashboardsLogic'
import { sceneLogic } from 'scenes/sceneLogic'
import { Scene } from 'scenes/sceneTypes'
import { urls } from 'scenes/urls'

import { projectTreeDataLogic } from '~/layout/panel-layout/ProjectTree/projectTreeDataLogic'
import { useMocks } from '~/mocks/jest'
import { dashboardsModel } from '~/models/dashboardsModel'
import { initKeaTests } from '~/test/init'
import { AppContext, DashboardBasicType, DashboardType, UserBasicType } from '~/types'

import dashboardJson from '../__mocks__/dashboard.json'

let dashboardId = 1234
const dashboard = (extras: Partial<DashboardType>): DashboardType => {
    dashboardId = dashboardId + 1
    return {
        ...dashboardJson,
        id: dashboardId,
        name: 'Test dashboard: ' + dashboardId,
        ...extras,
    } as any as DashboardType
}

const blankScene = (): any => ({ scene: { component: () => null, logic: null } })
const scenes: any = { [Scene.Dashboards]: blankScene }

describe('dashboardsLogic', () => {
    let logic: ReturnType<typeof dashboardsLogic.build>

    const allDashboards = [
        { ...dashboard({ created_by: { uuid: 'USER_UUID' } as UserBasicType, is_shared: true }) },
        { ...dashboard({ created_by: { uuid: 'USER_UUID' } as UserBasicType, pinned: true }) },
        { ...dashboard({ created_by: { uuid: 'user2' } as UserBasicType, pinned: true }) },
        {
            ...dashboard({
                created_by: { uuid: 'USER_UUID' } as UserBasicType,
                is_shared: true,
                pinned: true,
            }),
        },
        { ...dashboard({ created_by: { uuid: 'USER_UUID' } as UserBasicType }) },
        { ...dashboard({ created_by: { uuid: 'user2' } as UserBasicType, name: 'needle' }) },
        {
            ...dashboard({
                created_by: { uuid: 'USER_UUID' } as UserBasicType,
                name: 'VMS Feature - History Browser - Nova',
            }),
        },
    ]

    beforeEach(async () => {
        window.POSTHOG_APP_CONTEXT = { current_user: MOCK_DEFAULT_USER } as unknown as AppContext

        useMocks({
            get: {
                '/api/environments/:team_id/dashboards/': {
                    count: 7,
                    next: null,
                    previous: null,
                    results: allDashboards,
                },
            },
        })

        initKeaTests()

        dashboardsModel.mount()
        projectTreeDataLogic.mount()
        await expectLogic(dashboardsModel).toDispatchActions(['loadDashboardsSuccess'])
        sceneLogic({ scenes }).mount()
        sceneLogic.actions.setTabs([
            { id: '1', title: '...', pathname: '/', search: '', hash: '', active: true, iconType: 'blank' },
        ])

        logic = dashboardsLogic({ tabId: '1' })
        logic.mount()
    })

    it('shows all dashboards when no filters', async () => {
        expect(logic.values.dashboards).toHaveLength(allDashboards.length)
    })

    it('shows correct dashboards when on pinned tab', async () => {
        expectLogic(logic, () => {
            logic.actions.setCurrentTab(DashboardsTab.Pinned)
        }).toMatchValues({
            dashboards: truth((dashboards: DashboardType[]) => {
                return dashboards.length === 3 && dashboards.every((d) => d.pinned)
            }),
        })
    })

    it('shows correct dashboards when on my tab', async () => {
        expectLogic(logic, () => {
            logic.actions.setCurrentTab(DashboardsTab.Yours)
        }).toMatchValues({
            dashboards: truth((dashboards: DashboardType[]) => {
                return dashboards.length === 5 && dashboards.every((d) => d.created_by?.uuid === 'USER_UUID')
            }),
        })
    })

    it('shows no dashboards on starred tab when there are no shortcuts', async () => {
        expectLogic(logic, () => {
            logic.actions.setCurrentTab(DashboardsTab.Starred)
        }).toMatchValues({
            dashboards: [],
        })
    })

    it('shows correct dashboards when filtering by name', async () => {
        expectLogic(logic, () => {
            logic.actions.setFilters({ createdBy: 'user2' })
        }).toMatchValues({
            dashboards: truth((dashboards: DashboardType[]) => {
                return (
                    dashboards.length === 2 &&
                    dashboards[0].created_by?.uuid === 'user2' &&
                    dashboards[1].created_by?.uuid === 'user2'
                )
            }),
        })
    })

    it('shows correct dashboards when filtering by name and shared', async () => {
        expectLogic(logic, () => {
            logic.actions.setFilters({ createdBy: 'user2', shared: true })
        }).toMatchValues({
            dashboards: [],
        })
    })

    it('shows correct dashboards when filtering by name and on pinned tab', async () => {
        expectLogic(logic, () => {
            logic.actions.setCurrentTab(DashboardsTab.Pinned)
            logic.actions.setFilters({ createdBy: 'user2' })
        }).toMatchValues({
            dashboards: truth((dashboards: DashboardType[]) => {
                return dashboards.length === 1 && dashboards[0].pinned
            }),
        })
    })

    it('shows correct dashboards filtering by shared and on pinned tab', async () => {
        expectLogic(logic, () => {
            logic.actions.setCurrentTab(DashboardsTab.Pinned)
            logic.actions.setFilters({ shared: true })
        }).toMatchValues({
            dashboards: truth((dashboards: DashboardType[]) => {
                return (
                    dashboards.length === 1 &&
                    dashboards.every((d) => d.pinned && d.is_shared) &&
                    dashboards[0].created_by?.uuid === 'USER_UUID'
                )
            }),
        })
    })

    it('shows correct dashboards when searching by name', async () => {
        expectLogic(logic, () => {
            logic.actions.setCurrentTab(DashboardsTab.Pinned)
            logic.actions.setFilters({ shared: true })
        }).toMatchValues({
            dashboards: truth((dashboards: DashboardType[]) => {
                return (
                    dashboards.length === 1 &&
                    dashboards.every((d) => d.pinned && d.is_shared) &&
                    dashboards[0].created_by?.uuid === 'USER_UUID'
                )
            }),
        })
    })

    it('shows correct dashboards when searching', async () => {
        expectLogic(logic, () => {
            logic.actions.setFilters({ search: 'needl' })
        }).toMatchValues({
            dashboards: truth((dashboards: DashboardType[]) => {
                return dashboards.length === 1 && dashboards[0].name === 'needle'
            }),
        })
    })

    it.each([['Nova'], ['nova'], ['NOVA']])(
        'search matches a token at the end of a long dashboard name — case "%s"',
        (search) => {
            expectLogic(logic, () => {
                logic.actions.setFilters({ search })
            }).toMatchValues({
                dashboards: truth((dashboards: DashboardType[]) => {
                    return dashboards.length === 1 && dashboards[0].name === 'VMS Feature - History Browser - Nova'
                }),
            })
        }
    )

    it('syncs search to URL when setSearch is called', async () => {
        await expectLogic(logic, () => {
            logic.actions.setSearch('needle')
        })

        expect(router.values.searchParams.search).toBe('needle')
    })

    it('removes search param from URL when search is cleared', async () => {
        await expectLogic(logic, () => {
            logic.actions.setSearch('needle')
        })

        await expectLogic(logic, () => {
            logic.actions.setSearch('')
        })

        expect(router.values.searchParams.search).toBeUndefined()
    })

    it('loads search from URL into filters on mount', async () => {
        // Recreate logic with URL containing a search param
        logic.unmount()
        router.actions.push(urls.dashboards(), { search: 'needle' })
        logic = dashboardsLogic({ tabId: '1' })
        logic.mount()

        await expectLogic(logic).toMatchValues({
            filters: expect.objectContaining({ search: 'needle' }),
        })
    })

    it('defaults invalid tab URL param to All', async () => {
        logic.unmount()
        router.actions.push(urls.dashboards(), { tab: 'not-a-real-tab' })
        logic = dashboardsLogic({ tabId: '1' })
        logic.mount()

        await expectLogic(logic).toMatchValues({
            currentTab: DashboardsTab.All,
        })
    })
})

function listOrderRow(id: number, name: string, pinned = false): DashboardBasicType {
    return { id, name, pinned } as DashboardBasicType
}

describe('compareDashboardsListDefaultOrder', () => {
    it('orders starred+pinned before starred+unpinned', () => {
        const starred = new Set([1, 2])
        expect(
            compareDashboardsListDefaultOrder(listOrderRow(1, 'Z', true), listOrderRow(2, 'A', false), starred)
        ).toBeLessThan(0)
        expect(
            compareDashboardsListDefaultOrder(listOrderRow(2, 'A', false), listOrderRow(1, 'Z', true), starred)
        ).toBeGreaterThan(0)
    })

    it('orders starred+unpinned before non-starred+pinned (even when non-starred name sorts earlier)', () => {
        const starred = new Set([1])
        expect(
            compareDashboardsListDefaultOrder(listOrderRow(1, 'Z', false), listOrderRow(2, 'A', true), starred)
        ).toBeLessThan(0)
        expect(
            compareDashboardsListDefaultOrder(listOrderRow(2, 'A', true), listOrderRow(1, 'Z', false), starred)
        ).toBeGreaterThan(0)
    })

    it('orders non-starred+pinned before non-starred+unpinned (even when unpinned name sorts earlier)', () => {
        const empty = new Set<number>()
        expect(
            compareDashboardsListDefaultOrder(
                listOrderRow(10, 'Web Vitals', true),
                listOrderRow(20, 'Landing Pages Report', false),
                empty
            )
        ).toBeLessThan(0)
        expect(
            compareDashboardsListDefaultOrder(
                listOrderRow(20, 'Landing Pages Report', false),
                listOrderRow(10, 'Web Vitals', true),
                empty
            )
        ).toBeGreaterThan(0)
    })

    it.each([['Alpha', 'Beta', -1] as const, ['Beta', 'Alpha', 1] as const, ['same', 'same', 0] as const])(
        'within starred+pinned tier sorts by name then id (%s vs %s)',
        (aName, bName, sign) => {
            const starred = new Set([1, 2])
            const a = listOrderRow(1, aName, true)
            const b = listOrderRow(2, bName, true)
            const cmp = compareDashboardsListDefaultOrder(a, b, starred)
            if (sign < 0) {
                expect(cmp).toBeLessThan(0)
            } else if (sign > 0) {
                expect(cmp).toBeGreaterThan(0)
            } else {
                expect(cmp).toBeLessThan(0)
            }
        }
    )

    it('ties duplicate title in the same tier by id', () => {
        const empty = new Set<number>()
        expect(
            compareDashboardsListDefaultOrder(
                listOrderRow(4, 'API usage metrics', true),
                listOrderRow(7, 'API usage metrics', true),
                empty
            )
        ).toBeLessThan(0)
        expect(
            compareDashboardsListDefaultOrder(
                listOrderRow(9, 'API usage metrics', false),
                listOrderRow(8, 'API usage metrics', false),
                empty
            )
        ).toBeGreaterThan(0)
    })

    it('regression: multi-tier list sorts into 0→1→2→3 then A–Z within tier', () => {
        const starred = new Set([1, 2, 3])
        const dashboards = [
            listOrderRow(5, 'Zebra unpinned', false),
            listOrderRow(3, 'Starred unpinned', false),
            listOrderRow(6, 'Aardvark unpinned', false),
            listOrderRow(2, 'Starred pinned B', true),
            listOrderRow(1, 'Starred pinned A', true),
            listOrderRow(4, 'Pinned only', true),
        ]
        const sorted = [...dashboards].sort((a, b) => compareDashboardsListDefaultOrder(a, b, starred))
        expect(sorted.map((d) => d.id)).toEqual([1, 2, 3, 4, 6, 5])
    })
})
