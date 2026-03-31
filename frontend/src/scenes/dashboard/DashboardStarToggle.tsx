import { useActions, useValues } from 'kea'
import { useEffect, useMemo, useState } from 'react'

import { IconStar, IconStarFilled } from '@posthog/icons'

import { LemonButton } from 'lib/lemon-ui/LemonButton'

import { projectTreeDataLogic } from '~/layout/panel-layout/ProjectTree/projectTreeDataLogic'
import { FileSystemEntry } from '~/queries/schema/schema-general'

import { buildDashboardShortcutFileEntry } from './dashboardShortcutEntry'

export function dashboardShortcutIdForDashboard(
    shortcutData: FileSystemEntry[],
    dashboardId: number
): string | undefined {
    for (const s of shortcutData) {
        if (s.type === 'dashboard' && s.ref) {
            const nid = parseInt(s.ref, 10)
            if (!Number.isNaN(nid) && nid === dashboardId) {
                return s.id
            }
        }
    }
    return undefined
}

export interface DashboardStarToggleProps {
    dashboardId: number
    /** Display name for shortcut label in starred list */
    name: string | null | undefined
    /** `data-attr` for analytics, e.g. `dashboards-list-star-toggle` or `dashboard-header-star-toggle` */
    dataAttr: string
}

export function DashboardStarToggle({ dashboardId, name, dataAttr }: DashboardStarToggleProps): JSX.Element {
    const { shortcutData } = useValues(projectTreeDataLogic)
    const { addShortcutItem, deleteShortcut } = useActions(projectTreeDataLogic)
    const [busy, setBusy] = useState(false)

    useEffect(() => {
        projectTreeDataLogic.actions.loadShortcuts()
    }, [])

    const shortcutId = useMemo(
        () => dashboardShortcutIdForDashboard(shortcutData, dashboardId),
        [shortcutData, dashboardId]
    )
    const isStarred = !!shortcutId

    const onClick = (): void => {
        if (busy) {
            return
        }
        setBusy(true)
        const pending = shortcutId
            ? deleteShortcut(shortcutId)
            : addShortcutItem(buildDashboardShortcutFileEntry(dashboardId, name))
        void Promise.resolve(pending as PromiseLike<unknown>).finally(() => setBusy(false))
    }

    return (
        <LemonButton
            data-attr={dataAttr}
            data-dashboard-id={dashboardId}
            data-starred={isStarred}
            loading={busy}
            size="small"
            onClick={onClick}
            tooltip={isStarred ? 'Remove from starred' : 'Add to starred'}
            icon={isStarred ? <IconStarFilled className="text-warning" /> : <IconStar className="text-tertiary" />}
        />
    )
}
