import { useValues } from 'kea'
import { router } from 'kea-router'
import { useEffect, useState } from 'react'

import { IconX } from '@posthog/icons'
import { LemonButton, LemonInput, LemonSelect } from '@posthog/lemon-ui'

import { getCookie } from 'lib/api'
import { BridgePage } from 'lib/components/BridgePage/BridgePage'
import { Spinner } from 'lib/lemon-ui/Spinner'
import { SceneExport } from 'scenes/sceneTypes'

export const scene: SceneExport = {
    component: VercelConnect,
}

interface Team {
    id: number
    name: string
    already_linked: boolean
}

interface Organization {
    id: string
    name: string
    already_linked: boolean
    teams: Team[]
}

interface SessionInfo {
    next_url: string
    organizations: Organization[]
}

type EnvMapping = Record<string, number | null>

const DEFAULT_ENVS = ['production', 'preview', 'development']

export function VercelConnect(): JSX.Element {
    const { searchParams } = useValues(router)
    const sessionKey = searchParams.session

    const [loading, setLoading] = useState(true)
    const [linking, setLinking] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [success, setSuccess] = useState(false)
    const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null)
    const [selectedOrg, setSelectedOrg] = useState<string | null>(null)
    const [envMapping, setEnvMapping] = useState<EnvMapping>({
        production: null,
        preview: null,
        development: null,
    })
    const [newEnvName, setNewEnvName] = useState('')
    const [linkedOrgName, setLinkedOrgName] = useState<string>('')

    useEffect(() => {
        if (!sessionKey) {
            setError('Missing session parameter. Please try again from Vercel.')
            setLoading(false)
            return
        }

        fetch(`/api/vercel/connect/session?session=${encodeURIComponent(sessionKey)}`)
            .then((res) => {
                if (!res.ok) {
                    throw new Error('Session expired or invalid')
                }
                return res.json()
            })
            .then((data: SessionInfo) => {
                setSessionInfo(data)
                const available = data.organizations.filter((o) => !o.already_linked)
                if (available.length === 1) {
                    setSelectedOrg(available[0].id)
                }
                setLoading(false)
            })
            .catch((err) => {
                setError(err.message || 'Failed to load session')
                setLoading(false)
            })
    }, [sessionKey])

    useEffect(() => {
        if (selectedOrg && sessionInfo) {
            const org = sessionInfo.organizations.find((o) => o.id === selectedOrg)
            const teams = org?.teams.filter((t) => !t.already_linked) || []
            if (teams.length === 1) {
                const id = teams[0].id
                setEnvMapping({ production: id, preview: id, development: id })
            } else {
                setEnvMapping({ production: null, preview: null, development: null })
            }
        }
    }, [selectedOrg, sessionInfo])

    const envNames = Object.keys(envMapping)

    const handleAddEnv = (): void => {
        const name = newEnvName.trim().toLowerCase().replace(/\s+/g, '-')
        if (!name || name in envMapping) {
            return
        }
        setEnvMapping((prev) => ({ ...prev, [name]: null }))
        setNewEnvName('')
    }

    const handleRemoveEnv = (env: string): void => {
        setEnvMapping((prev) => {
            const next = { ...prev }
            delete next[env]
            return next
        })
    }

    const handleLink = (): void => {
        if (!selectedOrg || !sessionKey) {
            return
        }

        setLinking(true)
        setError(null)

        const payload: Record<string, number> = {}
        for (const [env, teamId] of Object.entries(envMapping)) {
            payload[env] = teamId || envMapping.production!
        }

        fetch('/api/vercel/connect/complete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('posthog_csrftoken') || '',
            },
            body: JSON.stringify({
                session: sessionKey,
                organization_id: selectedOrg,
                environment_mapping: payload,
            }),
        })
            .then((res) => {
                if (!res.ok) {
                    return res.json().then((data) => {
                        throw new Error(data.detail || data.attr?.session || 'Failed to link')
                    })
                }
                return res.json()
            })
            .then((data) => {
                setLinkedOrgName(data.organization_name)
                setSuccess(true)
                setLinking(false)

                const returnUrl = data.next_url
                if (returnUrl) {
                    window.location.href = returnUrl
                }
            })
            .catch((err) => {
                setError(err.message || 'Failed to link organization')
                setLinking(false)
            })
    }

    const redirectUrl = sessionInfo?.next_url

    if (loading) {
        return (
            <BridgePage view="vercel-connect">
                <div className="text-center">
                    <Spinner className="text-4xl" />
                    <p className="mt-4">Loading...</p>
                </div>
            </BridgePage>
        )
    }

    if (success) {
        return (
            <BridgePage view="vercel-connect">
                <h2 className="text-center">Account linked</h2>
                <p className="text-center mb-6">
                    Your PostHog organization <strong>{linkedOrgName}</strong> is now connected to Vercel.
                </p>
                {redirectUrl ? (
                    <LemonButton
                        fullWidth
                        type="primary"
                        center
                        onClick={() => {
                            window.location.href = redirectUrl
                        }}
                    >
                        Return to Vercel
                    </LemonButton>
                ) : (
                    <LemonButton fullWidth type="primary" center to="/">
                        Go to PostHog
                    </LemonButton>
                )}
            </BridgePage>
        )
    }

    if (error && !sessionInfo) {
        return (
            <BridgePage view="vercel-connect">
                <h2 className="text-center">Something went wrong</h2>
                <p className="text-center text-danger mb-6">{error}</p>
                <LemonButton fullWidth type="secondary" center onClick={() => window.close()}>
                    Close
                </LemonButton>
            </BridgePage>
        )
    }

    const availableOrgs = sessionInfo?.organizations.filter((o) => !o.already_linked) || []
    const linkedOrgs = sessionInfo?.organizations.filter((o) => o.already_linked) || []
    const selectedOrgData = sessionInfo?.organizations.find((o) => o.id === selectedOrg)
    const availableTeams = selectedOrgData?.teams.filter((t) => !t.already_linked) || []

    return (
        <BridgePage view="vercel-connect">
            <h2 className="text-center">Connect to Vercel</h2>
            <p className="text-center mb-6">Select which PostHog organization to link to your Vercel account.</p>

            {error && <p className="text-danger text-center mb-4">{error}</p>}

            {availableOrgs.length === 0 ? (
                <div className="text-center mb-6">
                    <p className="text-muted">
                        {linkedOrgs.length > 0
                            ? 'All your organizations are already linked to Vercel.'
                            : "You don't have any organizations with admin access."}
                    </p>
                </div>
            ) : (
                <>
                    <div className="mb-6">
                        <LemonSelect
                            fullWidth
                            placeholder="Select an organization"
                            value={selectedOrg}
                            onChange={(value) => setSelectedOrg(value)}
                            options={availableOrgs.map((org) => ({
                                value: org.id,
                                label: org.name,
                            }))}
                        />
                    </div>

                    {selectedOrg && availableTeams.length > 0 && (
                        <div className="mb-6 space-y-3">
                            {envNames.map((env) => (
                                <div key={env} className="flex items-center gap-2">
                                    <label className="text-xs font-medium text-muted uppercase w-28 shrink-0">
                                        {env}
                                    </label>
                                    <LemonSelect
                                        fullWidth
                                        placeholder="Select a project"
                                        value={envMapping[env]}
                                        onChange={(value) => setEnvMapping((prev) => ({ ...prev, [env]: value }))}
                                        options={availableTeams.map((t) => ({
                                            value: t.id,
                                            label: t.name,
                                        }))}
                                    />
                                    {!DEFAULT_ENVS.includes(env) && (
                                        <LemonButton
                                            size="xsmall"
                                            icon={<IconX />}
                                            tooltip="Remove environment"
                                            onClick={() => handleRemoveEnv(env)}
                                        />
                                    )}
                                </div>
                            ))}
                            <div className="flex items-center gap-2">
                                <LemonInput
                                    size="small"
                                    placeholder="e.g. staging"
                                    value={newEnvName}
                                    onChange={setNewEnvName}
                                    onPressEnter={handleAddEnv}
                                    fullWidth
                                />
                                <LemonButton
                                    size="small"
                                    type="secondary"
                                    onClick={handleAddEnv}
                                    disabledReason={!newEnvName.trim() ? 'Enter environment name' : undefined}
                                >
                                    Add
                                </LemonButton>
                            </div>
                        </div>
                    )}

                    <LemonButton
                        fullWidth
                        type="primary"
                        center
                        disabled={!selectedOrg || !envMapping.production || linking}
                        loading={linking}
                        onClick={handleLink}
                    >
                        Connect organization
                    </LemonButton>
                </>
            )}

            <LemonButton fullWidth type="secondary" center className="mt-2" onClick={() => window.close()}>
                Cancel
            </LemonButton>
        </BridgePage>
    )
}

export default VercelConnect
