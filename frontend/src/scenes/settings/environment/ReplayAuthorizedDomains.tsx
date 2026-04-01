import { useActions, useValues } from 'kea'

import { LemonBanner, LemonButton } from '@posthog/lemon-ui'

import { AuthorizedUrlList } from 'lib/components/AuthorizedUrlList/AuthorizedUrlList'
import { AuthorizedUrlListType } from 'lib/components/AuthorizedUrlList/authorizedUrlListLogic'
import { RestrictionScope, useRestrictedArea } from 'lib/components/RestrictedArea'
import { TeamMembershipLevel } from 'lib/constants'
import { teamLogic } from 'scenes/teamLogic'

import { ReplayAuthorizedDomainsConvertModal } from './ReplayAuthorizedDomainsConvertModal'
import { replayAuthorizedDomainsMigrationModalLogic } from './replayAuthorizedDomainsMigrationModalLogic'

export function ReplayAuthorizedDomains(): JSX.Element {
    const { currentTeam, currentTeamLoading } = useValues(teamLogic)
    const { prepareAndOpenModalFromCurrentTeam } = useActions(replayAuthorizedDomainsMigrationModalLogic)
    const restrictedReason = useRestrictedArea({
        scope: RestrictionScope.Project,
        minimumAccessLevel: TeamMembershipLevel.Admin,
    })

    return (
        <div className="flex flex-col gap-y-2">
            <ReplayAuthorizedDomainsConvertModal />
            <LemonBanner type="warning">
                <strong>This setting is now deprecated and cannot be updated.</strong> Instead we recommend deleting the
                domains below and using URL triggers in your recording conditions to control which domains you record.
            </LemonBanner>
            <p>
                Domains and wildcard subdomains are allowed (e.g. <code>https://*.example.com</code>). However,
                wildcarded top-level domains cannot be used (for security reasons).
            </p>
            <div>
                <LemonButton
                    type="primary"
                    onClick={prepareAndOpenModalFromCurrentTeam}
                    disabledReason={
                        restrictedReason ??
                        (!currentTeam?.recording_domains?.length ? 'No authorized domains to convert' : undefined)
                    }
                    loading={currentTeamLoading}
                    tooltip="URL triggers give you more control over which pages are recorded and support regex matching"
                    data-attr="replay-authorized-domains-convert-to-url-triggers"
                >
                    Convert to URL triggers
                </LemonButton>
            </div>
            <AuthorizedUrlList
                type={AuthorizedUrlListType.RECORDING_DOMAINS}
                showLaunch={false}
                allowAdd={false}
                displaySuggestions={false}
            />
        </div>
    )
}
