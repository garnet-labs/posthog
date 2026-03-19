import { sourceWizardLogic } from './sourceWizardLogic'

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
