import Fuse from 'fuse.js'
import { actions, afterMount, connect, kea, path, reducers, selectors } from 'kea'
import { router } from 'kea-router'

import { Sorting } from 'lib/lemon-ui/LemonTable/sorting'
import { featureFlagLogic } from 'lib/logic/featureFlagLogic'
import { tabAwareActionToUrl } from 'lib/logic/scenes/tabAwareActionToUrl'
import { tabAwareScene } from 'lib/logic/scenes/tabAwareScene'
import { tabAwareUrlToAction } from 'lib/logic/scenes/tabAwareUrlToAction'
import { objectClean } from 'lib/utils'
import { userLogic } from 'scenes/userLogic'

import { SIDE_PANEL_CONTEXT_KEY, SidePanelSceneContext } from '~/layout/navigation-3000/sidepanel/types'
import { projectTreeDataLogic } from '~/layout/panel-layout/ProjectTree/projectTreeDataLogic'
import { dashboardsModel } from '~/models/dashboardsModel'
import { tagsModel } from '~/models/tagsModel'
import { ActivityScope, Breadcrumb, DashboardBasicType } from '~/types'

import type { dashboardsLogicType } from './dashboardsLogicType'

export enum DashboardsTab {
    All = 'all',
    Yours = 'yours',
    Pinned = 'pinned',
    Starred = 'starred',
    Templates = 'templates',
}

/** Default: Name ascending — same four-tier order as `compareDashboardsListDefaultOrder` (id tie-break for duplicate titles). */
const DEFAULT_SORTING: Sorting = { columnKey: 'name', order: 1 }

export interface DashboardsFilters {
    search: string
    createdBy: string
    pinned: boolean
    shared: boolean
    starred: boolean
    tags?: string[]
}

export const DEFAULT_FILTERS: DashboardsFilters = {
    search: '',
    createdBy: 'All users',
    pinned: false,
    shared: false,
    starred: false,
    tags: [],
}

export function starredDashboardIdsFromShortcuts(shortcutData: { type?: string; ref?: string | null }[]): Set<number> {
    return new Set(
        shortcutData.flatMap((s) => {
            if (s.type !== 'dashboard' || !s.ref) {
                return []
            }
            const id = parseInt(s.ref, 10)
            return Number.isNaN(id) ? [] : [id]
        })
    )
}

/**
 * Dashboards list order (then title A–Z within a tier; duplicate titles tie-break by id):
 * starred+pinned → starred+unpinned → non-starred+pinned → non-starred+unpinned.
 */
export function compareDashboardsListDefaultOrder(
    a: DashboardBasicType,
    b: DashboardBasicType,
    starredIds: Set<number>
): number {
    const tier = (d: DashboardBasicType): number => {
        if (starredIds.has(d.id)) {
            return d.pinned ? 0 : 1
        }
        return d.pinned ? 2 : 3
    }
    const tierDiff = tier(a) - tier(b)
    if (tierDiff !== 0) {
        return tierDiff
    }
    const nameDiff = (a.name ?? 'Untitled').localeCompare(b.name ?? 'Untitled')
    if (nameDiff !== 0) {
        return nameDiff
    }
    return a.id - b.id
}

export type DashboardFuse = Fuse<DashboardBasicType> // This is exported for kea-typegen

export const dashboardsLogic = kea<dashboardsLogicType>([
    path(['scenes', 'dashboard', 'dashboardsLogic']),
    tabAwareScene(),
    connect(() => ({
        values: [
            userLogic,
            ['user'],
            featureFlagLogic,
            ['featureFlags'],
            tagsModel,
            ['tags'],
            projectTreeDataLogic,
            ['shortcutData'],
        ],
    })),
    actions({
        setCurrentTab: (tab: DashboardsTab) => ({ tab }),
        setSearch: (search: string) => ({ search }),
        setFilters: (filters: Partial<DashboardsFilters>) => ({
            filters,
        }),
        tableSortingChanged: (sorting: Sorting | null) => ({
            sorting,
        }),
        setTagSearch: (search: string) => ({ search }),
        setShowTagPopover: (visible: boolean) => ({ visible }),
    }),
    reducers({
        tableSorting: [
            DEFAULT_SORTING,
            { persist: true },
            {
                tableSortingChanged: (_state: Sorting | null, { sorting }: { sorting: Sorting | null }) =>
                    sorting ?? null,
            },
            // Kea's generated reducer typing is Sorting-only; null clears column sort (dataSource order from `compareDashboardsListDefaultOrder`).
        ] as any,
        currentTab: [
            DashboardsTab.All as DashboardsTab,
            {
                setCurrentTab: (_, { tab }) => tab,
            },
        ],

        filters: [
            DEFAULT_FILTERS,
            {
                setFilters: (state, { filters }) =>
                    objectClean({
                        ...state,
                        ...filters,
                    }),
            },
        ],
        tagSearch: [
            '',
            {
                setTagSearch: (_, { search }) => search,
                setShowTagPopover: (state, { visible }) => (visible ? state : ''),
            },
        ],
        showTagPopover: [
            false,
            {
                setShowTagPopover: (_, { visible }) => visible,
            },
        ],
    }),

    selectors({
        isFiltering: [
            (s) => [s.filters],
            (filters) => {
                return Object.keys(filters).some((key) => {
                    const filterKey = key as keyof DashboardsFilters
                    return filters[filterKey] !== DEFAULT_FILTERS[filterKey]
                })
            },
        ],
        /** LemonTable empty copy: tab-only empty (e.g. Starred) must not say "filters" when `isFiltering` is false. */
        dashboardsTableEmptyState: [
            (s) => [s.currentTab, s.isFiltering],
            (currentTab: DashboardsTab, isFiltering: boolean) => {
                if (isFiltering) {
                    return 'No dashboards matching your filters!'
                }
                if (currentTab === DashboardsTab.Starred) {
                    return 'No starred dashboards yet. Star one from the All dashboards tab to see it here.'
                }
                if (currentTab === DashboardsTab.Pinned) {
                    return 'No pinned dashboards.'
                }
                if (currentTab === DashboardsTab.Yours) {
                    return 'No dashboards created by you.'
                }
                return 'No dashboards matching your filters!'
            },
        ],
        filteredTags: [
            (s) => [s.tags, s.tagSearch],
            (tags, search) => {
                if (!search) {
                    return tags || []
                }
                return (tags || []).filter((tag) => tag.toLowerCase().includes(search.toLowerCase()))
            },
        ],
        dashboards: [
            (s) => [
                dashboardsModel.selectors.nameSortedDashboards,
                s.filters,
                s.fuse,
                s.currentTab,
                s.user,
                s.shortcutData,
            ],
            (dashboards, filters, fuse, currentTab, user, shortcutData) => {
                const starredIds = starredDashboardIdsFromShortcuts(shortcutData ?? [])
                let haystack = dashboards
                if (filters.search) {
                    haystack = fuse.search(filters.search).map((result) => result.item)
                }
                if (currentTab === DashboardsTab.Pinned) {
                    haystack = haystack.filter((d) => d.pinned)
                }
                if (currentTab === DashboardsTab.Starred) {
                    haystack = haystack.filter((d) => starredIds.has(d.id))
                }
                if (filters.pinned) {
                    haystack = haystack.filter((d) => d.pinned)
                }
                if (filters.starred) {
                    haystack = haystack.filter((d) => starredIds.has(d.id))
                }
                if (filters.shared) {
                    haystack = haystack.filter((d) => d.is_shared)
                }
                if (currentTab === DashboardsTab.Yours) {
                    haystack = haystack.filter((d) => d.created_by?.uuid === user?.uuid)
                } else if (filters.createdBy !== 'All users') {
                    haystack = haystack.filter((d) => d.created_by?.uuid === filters.createdBy)
                }
                if (filters.tags && filters.tags.length > 0) {
                    haystack = haystack.filter((d) => filters.tags?.some((tag) => d.tags?.includes(tag)))
                }
                return [...haystack].sort((a, b) => compareDashboardsListDefaultOrder(a, b, starredIds))
            },
        ],

        fuse: [
            () => [dashboardsModel.selectors.nameSortedDashboards],
            (dashboards): DashboardFuse => {
                return new Fuse<DashboardBasicType>(dashboards, {
                    keys: ['key', 'name', 'description', 'tags'],
                    threshold: 0.3,
                    // Without this, Fuse favors matches near the start of each field; tail tokens on long titles often miss `threshold`.
                    ignoreLocation: true,
                })
            },
        ],

        breadcrumbs: [
            () => [],
            (): Breadcrumb[] => [
                {
                    key: 'dashboards',
                    name: 'Dashboards',
                    iconType: 'dashboard',
                },
            ],
        ],
        [SIDE_PANEL_CONTEXT_KEY]: [
            () => [],
            (): SidePanelSceneContext => ({
                activity_scope: ActivityScope.DASHBOARD,
            }),
        ],
    }),
    tabAwareActionToUrl(({ values }) => ({
        setCurrentTab: () => {
            const tab = values.currentTab === DashboardsTab.All ? undefined : values.currentTab
            if (router.values.searchParams['tab'] === tab) {
                return
            }

            router.actions.push(router.values.location.pathname, { ...router.values.searchParams, tab })
        },
        setSearch: ({ search }) => {
            const nextSearch = search ?? ''
            const currentSearch = (router.values.searchParams['search'] as string | undefined) ?? ''

            if (nextSearch === currentSearch) {
                return
            }

            const searchParams: Record<string, any> = { ...router.values.searchParams }

            if (nextSearch) {
                searchParams['search'] = nextSearch
            } else {
                delete searchParams['search']
            }

            return [router.values.location.pathname, searchParams, router.values.hashParams, { replace: true }]
        },
    })),
    tabAwareUrlToAction(({ actions }) => ({
        '/dashboard': (_, searchParams) => {
            const rawTab = searchParams['tab']
            const tab =
                typeof rawTab === 'string' && (Object.values(DashboardsTab) as string[]).includes(rawTab)
                    ? (rawTab as DashboardsTab)
                    : DashboardsTab.All
            actions.setCurrentTab(tab)

            const search = typeof searchParams['search'] === 'string' ? searchParams['search'] : ''
            actions.setFilters({ search })
        },
    })),
    afterMount(() => {
        projectTreeDataLogic.actions.loadShortcuts()
    }),
])
