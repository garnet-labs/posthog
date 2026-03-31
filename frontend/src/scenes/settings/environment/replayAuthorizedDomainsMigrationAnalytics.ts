import posthog from 'posthog-js'

import type { UrlTriggerConfig } from 'lib/components/IngestionControls/types'

import type { AuthorizedDomainsMigrationSnapshot, MigrationRow } from './replayAuthorizedDomainsMigrationTypes'

function serializeTriggersForEvent(config: UrlTriggerConfig[]): { url: string; matching: string }[] {
    return config.map((t) => ({ url: t.url, matching: t.matching }))
}

export function reportReplayAuthorizedDomainsMigrationComplete(props: {
    teamId: number | undefined
    snapshot: AuthorizedDomainsMigrationSnapshot
    rows: MigrationRow[]
    merged: UrlTriggerConfig[]
}): void {
    posthog.capture('replay_authorized_domains_converted_to_url_triggers', {
        team_id: props.teamId,
        recording_domains_before: props.snapshot.recording_domains,
        session_recording_url_trigger_config_before: serializeTriggersForEvent(
            props.snapshot.session_recording_url_trigger_config
        ),
        submitted_conversions: props.rows.map((r) => ({
            authorized_domain: r.domain,
            url_trigger_regex: r.pattern.trim(),
        })),
        session_recording_url_trigger_config_after_merge: serializeTriggersForEvent(props.merged),
    })
}
