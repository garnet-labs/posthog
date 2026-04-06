import { useActions, useValues } from 'kea'
import posthog from 'posthog-js'

import { IconCopy, IconLock } from '@posthog/icons'
import { LemonBanner, LemonButton, LemonDivider, LemonModal, LemonSkeleton, LemonSwitch } from '@posthog/lemon-ui'

import { AccessControlAction } from 'lib/components/AccessControlAction'
import { SharePasswordsTable } from 'lib/components/Sharing/SharePasswordsTable'
import { sharingLogic } from 'lib/components/Sharing/sharingLogic'
import { SHARING_MODAL_WIDTH } from 'lib/components/Sharing/SharingModal'
import { upgradeModalLogic } from 'lib/components/UpgradeModal/upgradeModalLogic'
import { FEATURE_FLAGS } from 'lib/constants'
import { Tooltip } from 'lib/lemon-ui/Tooltip'
import { featureFlagLogic } from 'lib/logic/featureFlagLogic'
import { base64Encode } from 'lib/utils'
import { accessLevelSatisfied } from 'lib/utils/accessControlUtils'
import { copyToClipboard } from 'lib/utils/copyToClipboard'
import { urls } from 'scenes/urls'

import { AccessControlPopoutCTA } from '~/layout/navigation-3000/sidepanel/panels/access_control/AccessControlPopoutCTA'
import { AccessControlLevel, AccessControlResourceType, AvailableFeature } from '~/types'

import { notebookLogic } from './notebookLogic'

export type NotebookShareModalProps = {
    shortId: string
}

export function NotebookShareModal({ shortId }: NotebookShareModalProps): JSX.Element {
    const nbLogic = notebookLogic({ shortId })
    const { content, isLocalOnly, isShareModalOpen, notebook } = useValues(nbLogic)
    const { closeShareModal } = useActions(nbLogic)
    const userAccessLevel = notebook?.user_access_level

    const notebookUrl = urls.absolute(urls.currentProject(urls.notebook(shortId)))
    const canvasUrl = urls.absolute(urls.canvas()) + `#🦔=${base64Encode(JSON.stringify(content))}`

    const sharingProps = { notebookShortId: shortId }
    const {
        sharingConfiguration,
        sharingConfigurationLoading,
        shareLink,
        sharingAllowed,
        advancedPermissionsAvailable,
    } = useValues(sharingLogic(sharingProps))
    const { setIsEnabled, setPasswordRequired } = useActions(sharingLogic(sharingProps))
    const { guardAvailableFeature } = useValues(upgradeModalLogic)
    const { featureFlags } = useValues(featureFlagLogic)
    const passwordProtectedSharesEnabled = !!featureFlags[FEATURE_FLAGS.PASSWORD_PROTECTED_SHARES]

    const hasEditAccess = userAccessLevel
        ? accessLevelSatisfied(AccessControlResourceType.Notebook, userAccessLevel, AccessControlLevel.Editor)
        : true

    return (
        <LemonModal
            title="Share notebook"
            onClose={() => closeShareModal()}
            isOpen={isShareModalOpen}
            width={SHARING_MODAL_WIDTH}
            footer={
                <LemonButton type="secondary" onClick={closeShareModal}>
                    Done
                </LemonButton>
            }
        >
            <div className="deprecated-space-y-4">
                <AccessControlPopoutCTA
                    resourceType={AccessControlResourceType.Notebook}
                    callback={() => {
                        closeShareModal()
                    }}
                />
                <LemonDivider />
                <h3>Internal link</h3>
                {!isLocalOnly ? (
                    <>
                        <p>
                            <b>Click the button below</b> to copy a direct link to this Notebook. Make sure the person
                            you share it with has access to this PostHog project.
                        </p>
                        <LemonButton
                            type="secondary"
                            fullWidth
                            center
                            truncate
                            sideIcon={<IconCopy />}
                            onClick={() => void copyToClipboard(notebookUrl, 'notebook link')}
                            title={notebookUrl}
                        >
                            {notebookUrl}
                        </LemonButton>

                        <LemonDivider className="my-4" />
                    </>
                ) : (
                    <LemonBanner type="info">
                        <p>This Notebook cannot be shared directly with others as it is only visible to you.</p>
                    </LemonBanner>
                )}

                <h3>Template link</h3>
                <p>
                    The link below will open a Canvas with the contents of this Notebook, allowing the receiver to view
                    it, edit it or create their own Notebook without affecting this one.
                </p>
                <LemonButton
                    type="secondary"
                    fullWidth
                    center
                    truncate
                    sideIcon={<IconCopy />}
                    onClick={() => void copyToClipboard(canvasUrl, 'canvas link')}
                    title={canvasUrl}
                >
                    {canvasUrl}
                </LemonButton>

                <LemonDivider className="my-4" />

                <h3>Public link</h3>
                {!isLocalOnly ? (
                    <>
                        {!sharingConfiguration && sharingConfigurationLoading ? (
                            <LemonSkeleton.Row repeat={3} />
                        ) : !sharingConfiguration ? (
                            <p>Something went wrong...</p>
                        ) : (
                            <>
                                {!sharingAllowed ? (
                                    <LemonBanner type="warning">
                                        Public sharing is disabled for this organization.
                                    </LemonBanner>
                                ) : (
                                    <AccessControlAction
                                        resourceType={AccessControlResourceType.Notebook}
                                        minAccessLevel={AccessControlLevel.Editor}
                                        userAccessLevel={userAccessLevel}
                                    >
                                        <LemonSwitch
                                            id="notebook-sharing-switch"
                                            label="Share notebook publicly (read-only)"
                                            checked={sharingConfiguration.enabled}
                                            data-attr="notebook-sharing-switch"
                                            onChange={(active) => setIsEnabled(active)}
                                            bordered
                                            fullWidth
                                            loading={sharingConfigurationLoading}
                                        />
                                    </AccessControlAction>
                                )}

                                {sharingAllowed && sharingConfiguration.enabled && sharingConfiguration.access_token ? (
                                    <div className="deprecated-space-y-2 mt-2">
                                        {passwordProtectedSharesEnabled && hasEditAccess && (
                                            <div className="LemonSwitch LemonSwitch--medium LemonSwitch--bordered LemonSwitch--full-width flex-col py-1.5">
                                                <LemonSwitch
                                                    className="px-0"
                                                    fullWidth
                                                    label={
                                                        <div className="flex items-center">
                                                            Password protect
                                                            {!advancedPermissionsAvailable && (
                                                                <Tooltip title="This is a premium feature, click to learn more.">
                                                                    <IconLock className="ml-1.5 text-muted text-lg" />
                                                                </Tooltip>
                                                            )}
                                                        </div>
                                                    }
                                                    onChange={(passwordRequired: boolean) => {
                                                        if (passwordRequired) {
                                                            guardAvailableFeature(
                                                                AvailableFeature.ADVANCED_PERMISSIONS,
                                                                () => setPasswordRequired(passwordRequired)
                                                            )
                                                        } else {
                                                            setPasswordRequired(passwordRequired)
                                                        }
                                                    }}
                                                    checked={sharingConfiguration.password_required}
                                                />
                                                {sharingConfiguration.password_required && (
                                                    <div className="mt-1 w-full">
                                                        <SharePasswordsTable notebookShortId={shortId} />
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                        <LemonButton
                                            data-attr="notebook-sharing-link-button"
                                            type="primary"
                                            onClick={() => {
                                                void copyToClipboard(shareLink, shareLink).catch((e) =>
                                                    posthog.captureException(
                                                        new Error(
                                                            'unexpected notebook sharing clipboard error: ' + e.message
                                                        )
                                                    )
                                                )
                                            }}
                                            icon={<IconCopy />}
                                            fullWidth
                                            center
                                            truncate
                                            title={shareLink}
                                        >
                                            {shareLink}
                                        </LemonButton>
                                        <p className="text-muted text-sm">
                                            Anyone with the link can view this notebook. Embedded queries use this
                                            project&apos;s data within the same permissions as other shared resources.
                                        </p>
                                    </div>
                                ) : null}
                            </>
                        )}
                    </>
                ) : (
                    <LemonBanner type="info">
                        <p>Public links are not available for notebooks that are only visible to you.</p>
                    </LemonBanner>
                )}
            </div>
        </LemonModal>
    )
}
