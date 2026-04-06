import { useValues } from 'kea'
import { useEffect, useState } from 'react'

import { LemonButton, LemonSelect } from '@posthog/lemon-ui'

import { getCookie } from 'lib/api'
import { IconOpenInNew } from 'lib/lemon-ui/icons'
import { organizationLogic } from 'scenes/organizationLogic'

import { IntegrationType } from '~/types'

type EnvMapping = {
    production: number | null
    preview: number | null
    development: number | null
}

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

    useEffect(() => {
        setMapping(envMapping)
        setDirty(false)
    }, [envMapping])

    const handleChange = (env: keyof EnvMapping, value: number | null): void => {
        setMapping((prev) => ({ ...prev, [env]: value }))
        setDirty(true)
    }

    const handleSave = (): void => {
        setSaving(true)
        setError(null)
        fetch(`/api/organizations/@current/integrations/${integration.id}/environment-mapping/`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('posthog_csrftoken') || '',
            },
            body: JSON.stringify({
                production: mapping.production,
                preview: mapping.preview || mapping.production,
                development: mapping.development || mapping.production,
            }),
        })
            .then((res) => {
                if (!res.ok) {
                    throw new Error('Failed to save')
                }
                setDirty(false)
            })
            .catch(() => setError('Failed to save environment mapping'))
            .finally(() => setSaving(false))
    }

    const teamOptions = teams.map((t) => ({
        value: t.id,
        label: t.name,
    }))

    return (
        <div className="basis-full border-t pt-3 mt-1 mx-2 mb-2 space-y-2">
            <h4 className="font-semibold text-xs text-muted">Environment mapping</h4>
            <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 items-center max-w-sm">
                {(['production', 'preview', 'development'] as const).map((env) => (
                    <>
                        <span key={`label-${env}`} className="text-xs font-medium text-muted uppercase">
                            {env}
                        </span>
                        <LemonSelect
                            key={env}
                            size="small"
                            fullWidth
                            value={mapping[env]}
                            onChange={(value) => handleChange(env, value)}
                            options={teamOptions}
                        />
                    </>
                ))}
            </div>
            {error && <p className="text-danger text-xs">{error}</p>}
            {dirty && (
                <LemonButton type="primary" size="small" loading={saving} onClick={handleSave}>
                    Save mapping
                </LemonButton>
            )}
        </div>
    )
}
