import { actions, connect, kea, listeners, path, reducers } from 'kea'

import { Link } from '@posthog/lemon-ui'

import { lemonToast } from 'lib/lemon-ui/LemonToast/LemonToast'
import { getApiErrorDetail } from 'lib/utils/getApiErrorDetail'
import { teamLogic } from 'scenes/teamLogic'
import { urls } from 'scenes/urls'

import {
    buildConvertRowsFromAuthorizedDomains,
    computeMigrationMerge,
    normalizeUrlTriggersFromTeam,
} from './recordingDomainToUrlTrigger'
import { reportReplayAuthorizedDomainsMigrationComplete } from './replayAuthorizedDomainsMigrationAnalytics'
import type { replayAuthorizedDomainsMigrationModalLogicType } from './replayAuthorizedDomainsMigrationModalLogicType'
import type { AuthorizedDomainsMigrationSnapshot, MigrationRow } from './replayAuthorizedDomainsMigrationTypes'

export type { AuthorizedDomainsMigrationSnapshot } from './replayAuthorizedDomainsMigrationTypes'

export const replayAuthorizedDomainsMigrationModalLogic = kea<replayAuthorizedDomainsMigrationModalLogicType>([
    path(['scenes', 'settings', 'environment', 'replayAuthorizedDomainsMigrationModalLogic']),
    connect(() => ({
        values: [teamLogic, ['currentTeam', 'currentTeamLoading']],
    })),
    actions({
        openMigrationModal: (snapshot: AuthorizedDomainsMigrationSnapshot) => ({ snapshot }),
        prepareAndOpenModalFromCurrentTeam: true,
        closeMigrationModal: true,
        setMigrationRowPattern: (index: number, pattern: string) => ({ index, pattern }),
        setMigrationRowErrors: (errors: (string | undefined)[]) => ({ errors }),
        submitConvertAndRemove: true,
        submitConvertAndRemoveComplete: true,
    }),
    reducers({
        migrationModalOpen: [
            false,
            {
                openMigrationModal: () => true,
                closeMigrationModal: () => false,
            },
        ],
        migrationSnapshot: [
            null as AuthorizedDomainsMigrationSnapshot | null,
            {
                openMigrationModal: (_, { snapshot }) => snapshot,
                closeMigrationModal: () => null,
            },
        ],
        migrationRows: [
            [] as MigrationRow[],
            {
                openMigrationModal: (_, { snapshot }) =>
                    buildConvertRowsFromAuthorizedDomains(snapshot.recording_domains),
                closeMigrationModal: () => [],
                setMigrationRowPattern: (rows, { index, pattern }) =>
                    rows.map((r, i) => (i === index ? { ...r, pattern } : r)),
            },
        ],
        migrationRowErrors: [
            [] as (string | undefined)[],
            {
                openMigrationModal: () => [],
                closeMigrationModal: () => [],
                setMigrationRowPattern: (errs, { index }) => {
                    const next = [...errs]
                    next[index] = undefined
                    return next
                },
                setMigrationRowErrors: (_, { errors }) => errors,
            },
        ],
        migrationSubmitting: [
            false,
            {
                submitConvertAndRemove: () => true,
                submitConvertAndRemoveComplete: () => false,
            },
        ],
    }),
    listeners(({ actions, values }) => ({
        prepareAndOpenModalFromCurrentTeam: () => {
            const team = values.currentTeam
            const raw = team?.recording_domains ?? []
            const recording_domains = raw.filter((d): d is string => typeof d === 'string' && d.trim() !== '')
            if (!recording_domains.length) {
                return
            }
            actions.openMigrationModal({
                recording_domains,
                session_recording_url_trigger_config: normalizeUrlTriggersFromTeam(
                    team?.session_recording_url_trigger_config
                ),
            })
        },
        submitConvertAndRemove: async () => {
            const snapshot = values.migrationSnapshot
            if (!snapshot?.recording_domains.length) {
                actions.submitConvertAndRemoveComplete()
                return
            }
            const mergeResult = computeMigrationMerge(
                values.migrationRows,
                values.currentTeam?.session_recording_url_trigger_config
            )
            if (!mergeResult.ok) {
                actions.setMigrationRowErrors(mergeResult.errors)
                actions.submitConvertAndRemoveComplete()
                return
            }
            try {
                await teamLogic.asyncActions.updateCurrentTeam({
                    session_recording_url_trigger_config: mergeResult.merged,
                    recording_domains: [],
                })
                reportReplayAuthorizedDomainsMigrationComplete({
                    teamId: values.currentTeam?.id,
                    snapshot,
                    rows: values.migrationRows,
                    merged: mergeResult.merged,
                })
                lemonToast.success(
                    <>
                        Authorized domains removed and URL triggers updated. Review under{' '}
                        <Link to={urls.settings('environment-replay', 'replay-triggers')}>Recording conditions</Link>.
                    </>
                )
                actions.closeMigrationModal()
            } catch (error: unknown) {
                lemonToast.error(getApiErrorDetail(error) || 'Could not update recording settings')
            } finally {
                actions.submitConvertAndRemoveComplete()
            }
        },
    })),
])
