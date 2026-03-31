import { useActions, useValues } from 'kea'
import { useEffect, useMemo, useState } from 'react'

import { IconStar, IconStarFilled } from '@posthog/icons'

import { LemonButton } from 'lib/lemon-ui/LemonButton'

import { projectTreeDataLogic } from '~/layout/panel-layout/ProjectTree/projectTreeDataLogic'
import { FileSystemEntry } from '~/queries/schema/schema-general'

import { buildDashboardShortcutFileEntry } from './dashboardShortcutEntry'

export const DASHBOARD_FAVORITE_TOGGLE_DATA_ATTR_ID = 'dashboard-favorite-toggle'

export function dashboardShortcutIdForDashboard(
    shortcutData: FileSystemEntry[],
    dashboardId: number
): string | undefined {
    const match = shortcutData.find((s) => {
        if (s.type !== 'dashboard' || !s.ref) {
            return false
        }
        const nid = parseInt(s.ref, 10)
        return !Number.isNaN(nid) && nid === dashboardId
    })
    return match?.id
}

export interface DashboardStarToggleProps {
    dashboardId: number
    /** Display name for shortcut label in starred list */
    name: string | null | undefined
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
        void Promise.resolve(pending).finally(() => setBusy(false))
    }

    return (
        <LemonButton
            data-attr={dataAttr}
            data-attr-id={DASHBOARD_FAVORITE_TOGGLE_DATA_ATTR_ID}
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
