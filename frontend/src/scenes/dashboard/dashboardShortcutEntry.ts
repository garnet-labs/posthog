import { urls } from 'scenes/urls'

import { escapePath } from '~/layout/panel-layout/ProjectTree/utils'
import { FileSystemEntry } from '~/queries/schema/schema-general'

/** Payload for `projectTreeDataLogic.addShortcutItem` to star a dashboard in the global / sidebar shortcuts list. */
export function buildDashboardShortcutFileEntry(dashboardId: number, name: string | null | undefined): FileSystemEntry {
    return {
        id: `dashboard-shortcut-${dashboardId}`,
        path: escapePath(name || 'Untitled'),
        type: 'dashboard',
        ref: String(dashboardId),
        href: urls.dashboard(dashboardId),
    }
}
