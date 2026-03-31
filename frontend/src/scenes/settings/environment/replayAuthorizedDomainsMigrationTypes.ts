import type { UrlTriggerConfig } from 'lib/components/IngestionControls/types'

export type AuthorizedDomainsMigrationSnapshot = {
    recording_domains: string[]
    session_recording_url_trigger_config: UrlTriggerConfig[]
}

export type MigrationRow = { domain: string; pattern: string }
