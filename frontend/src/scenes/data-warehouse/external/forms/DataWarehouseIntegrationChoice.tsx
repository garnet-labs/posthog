import {
    IntegrationChoice,
    IntegrationConfigureProps,
} from 'lib/components/CyclotronJob/integrations/IntegrationChoice'
import { urls } from 'scenes/urls'

import { SourceConfig } from '~/queries/schema/schema-general'

import { sourceWizardLogic } from '../../new/sourceWizardLogic'

const SESSION_STORAGE_KEY = 'sourceWizard_formState'

export function saveSourceFormState(): void {
    try {
        const formValues = sourceWizardLogic.values.sourceConnectionDetails
        sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(formValues))
    } catch {
        // sessionStorage may be unavailable
    }
}

export function restoreSourceFormState(): boolean {
    try {
        const saved = sessionStorage.getItem(SESSION_STORAGE_KEY)
        if (saved) {
            sessionStorage.removeItem(SESSION_STORAGE_KEY)
            const values = JSON.parse(saved)
            sourceWizardLogic.actions.setSourceConnectionDetailsValues(values)
            return true
        }
    } catch {
        // sessionStorage may be unavailable or data may be corrupted
    }
    return false
}

export type DataWarehouseIntegrationChoice = IntegrationConfigureProps & {
    sourceConfig: SourceConfig
}

export function DataWarehouseIntegrationChoice({
    sourceConfig,
    integration,
    ...props
}: DataWarehouseIntegrationChoice): JSX.Element {
    return (
        <IntegrationChoice
            {...props}
            integration={integration ?? sourceConfig.name.toLowerCase()}
            redirectUrl={urls.dataWarehouseSourceNew(sourceConfig.name.toLowerCase())}
            beforeRedirect={saveSourceFormState}
        />
    )
}
