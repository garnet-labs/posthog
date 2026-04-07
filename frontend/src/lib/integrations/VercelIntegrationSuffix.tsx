import { useValues } from 'kea'
import { Fragment, useEffect, useState } from 'react'

import { IconX } from '@posthog/icons'
import { LemonButton, LemonInput, LemonSelect } from '@posthog/lemon-ui'

import { getCookie } from 'lib/api'
import { IconOpenInNew } from 'lib/lemon-ui/icons'
import { organizationLogic } from 'scenes/organizationLogic'

import { IntegrationType } from '~/types'

type EnvMapping = Record<string, number | null>

const DEFAULT_ENVS = ['production', 'preview', 'development']

export function VercelIntegrationSuffix({ integration }: { integration: IntegrationType }): JSX.Element {
    const accountUrl = integration.config?.account?.url
    const accountName = integration.config?.account?.name
    const isConnectable = integration.config?.type === 'connectable'
    const envMapping: EnvMapping | undefined = integration.config?.environment_mapping

    if (!isConnectable) {
        if (!accountUrl) {
            return <></>
        }
        return (
            <LemonButton
                type="secondary"
                to={accountUrl}
                targetBlank
                sideIcon={<IconOpenInNew />}
                tooltip={accountName ? `Open ${accountName} in Vercel` : 'Open in Vercel'}
            >
                View in Vercel
            </LemonButton>
        )
    }

    const effectiveMapping = envMapping || { production: null, preview: null, development: null }
    return <VercelEnvMappingEditor integration={integration} envMapping={effectiveMapping} />
}

function VercelEnvMappingEditor({
    integration,
    envMapping,
}: {
    integration: IntegrationType
    envMapping: EnvMapping
}): JSX.Element {
    const { currentOrganization } = useValues(organizationLogic)
    const teams = currentOrganization?.teams || []

    const [mapping, setMapping] = useState<EnvMapping>(envMapping)
    const [saving, setSaving] = useState(false)
    const [dirty, setDirty] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [newEnvName, setNewEnvName] = useState('')

    useEffect(() => {
        setMapping(envMapping)
        setDirty(false)
    }, [envMapping])

    const envNames = Object.keys(mapping)

    const handleChange = (env: string, value: number | null): void => {
        setMapping((prev) => ({ ...prev, [env]: value }))
        setDirty(true)
    }

    const handleAddEnv = (): void => {
        const name = newEnvName.trim().toLowerCase().replace(/\s+/g, '-')
        if (!name || name in mapping) {
            return
        }
        setMapping((prev) => ({ ...prev, [name]: null }))
        setNewEnvName('')
        setDirty(true)
    }

    const handleRemoveEnv = (env: string): void => {
        setMapping((prev) => {
            const next = { ...prev }
            delete next[env]
            return next
        })
        setDirty(true)
    }

    const handleSave = async (): Promise<void> => {
        setSaving(true)
        setError(null)
        try {
            const payload: Record<string, number> = {}
            for (const [env, teamId] of Object.entries(mapping)) {
                payload[env] = teamId || mapping.production!
            }
            const res = await fetch(`/api/organizations/@current/integrations/${integration.id}/environment-mapping/`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('posthog_csrftoken') || '',
                },
                body: JSON.stringify(payload),
            })
            if (!res.ok) {
                throw new Error('Failed to save')
            }
            setDirty(false)
        } catch {
            setError('Failed to save environment mapping')
        } finally {
            setSaving(false)
        }
    }

    const teamOptions = teams.map((t) => ({
        value: t.id,
        label: t.name,
    }))

    return (
        <div className="basis-full border-t pt-3 mt-1 mx-2 mb-2 space-y-2">
            <h4 className="font-semibold text-xs text-muted">Environment mapping</h4>
            <div className="grid grid-cols-[auto_1fr_auto] gap-x-3 gap-y-1.5 items-center max-w-sm">
                {envNames.map((env) => (
                    <Fragment key={env}>
                        <span className="text-xs font-medium text-muted uppercase">{env}</span>
                        <LemonSelect
                            size="small"
                            fullWidth
                            value={mapping[env]}
                            onChange={(value) => handleChange(env, value)}
                            options={teamOptions}
                        />
                        {DEFAULT_ENVS.includes(env) ? (
                            <span className="w-6" />
                        ) : (
                            <LemonButton
                                size="xsmall"
                                icon={<IconX />}
                                tooltip="Remove environment"
                                onClick={() => handleRemoveEnv(env)}
                            />
                        )}
                    </Fragment>
                ))}
            </div>
            <div className="flex items-center gap-2 max-w-sm">
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
            {error && <p className="text-danger text-xs">{error}</p>}
            {dirty && (
                <LemonButton
                    type="primary"
                    size="small"
                    loading={saving}
                    disabledReason={!mapping.production ? 'Production project is required' : undefined}
                    onClick={handleSave}
                >
                    Save mapping
                </LemonButton>
            )}
        </div>
    )
}
