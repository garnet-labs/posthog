import { useActions, useValues } from 'kea'

import { LemonButton, LemonInput, LemonLabel, LemonModal } from '@posthog/lemon-ui'

import { replayAuthorizedDomainsMigrationModalLogic } from './replayAuthorizedDomainsMigrationModalLogic'

export function ReplayAuthorizedDomainsConvertModal(): JSX.Element {
    const { migrationModalOpen, migrationRows, migrationRowErrors, migrationSubmitting, currentTeamLoading } =
        useValues(replayAuthorizedDomainsMigrationModalLogic)
    const { closeMigrationModal, setMigrationRowPattern, submitConvertAndRemove } = useActions(
        replayAuthorizedDomainsMigrationModalLogic
    )

    return (
        <LemonModal
            isOpen={migrationModalOpen}
            onClose={closeMigrationModal}
            width={720}
            title="Convert authorized domains to URL triggers"
            description="Each domain becomes one regex URL trigger. Adjust patterns if needed, then confirm. Your deprecated authorized domains list will be cleared."
            hasUnsavedInput={migrationModalOpen}
            footer={
                <div className="flex justify-end gap-2 w-full">
                    <LemonButton type="secondary" onClick={closeMigrationModal} disabled={migrationSubmitting}>
                        Cancel
                    </LemonButton>
                    <LemonButton
                        type="primary"
                        status="danger"
                        onClick={submitConvertAndRemove}
                        loading={migrationSubmitting || currentTeamLoading}
                        data-attr="replay-authorized-domains-convert-and-remove"
                    >
                        Convert and remove
                    </LemonButton>
                </div>
            }
        >
            <div className="flex flex-col gap-4">
                {migrationRows.map((row, index) => (
                    <div key={index} className="border border-border rounded p-3 flex flex-col gap-2">
                        <div>
                            <div className="text-xs text-muted font-semibold uppercase tracking-wide mb-1">
                                Authorized domain
                            </div>
                            <code className="text-sm break-all">{row.domain}</code>
                        </div>
                        <div>
                            <LemonLabel className="mb-1">URL trigger (regex)</LemonLabel>
                            <LemonInput
                                value={row.pattern}
                                onChange={(value) => setMigrationRowPattern(index, value)}
                                className="font-mono text-sm"
                                fullWidth
                            />
                            {migrationRowErrors[index] ? (
                                <p className="text-danger text-sm mt-1 mb-0">{migrationRowErrors[index]}</p>
                            ) : null}
                        </div>
                    </div>
                ))}
            </div>
        </LemonModal>
    )
}
