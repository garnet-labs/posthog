import Fuse from 'fuse.js'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { LemonCheckbox, LemonInput, LemonLabel, LemonSelect } from '@posthog/lemon-ui'

import api from 'lib/api'
import { LemonSwitch } from 'lib/lemon-ui/LemonSwitch'

import { DashboardWidgetType } from '~/types'

const CONTROLS_DESCRIPTIONS: Partial<Record<DashboardWidgetType, string>> = {
    [DashboardWidgetType.FeatureFlag]: 'Toggle the flag on or off directly from the dashboard',
    [DashboardWidgetType.Experiment]: 'Ship winning variants or stop experiments inline',
    [DashboardWidgetType.ErrorTracking]: 'Resolve and suppress errors without leaving the dashboard',
    [DashboardWidgetType.SurveyResponses]: 'Launch, pause, and resume surveys inline',
}

function ControlsToggle({
    enabled,
    onChange,
    widgetType,
}: {
    enabled: boolean
    onChange: (enabled: boolean) => void
    widgetType: DashboardWidgetType
}): JSX.Element | null {
    const description = CONTROLS_DESCRIPTIONS[widgetType]
    if (!description) {
        return null
    }
    return (
        <div className="flex items-start gap-3 p-3 rounded-lg border border-border">
            <div className="flex-1">
                <LemonLabel>Enable controls</LemonLabel>
                <p className="text-xs text-muted mt-0.5">{description}</p>
            </div>
            <LemonSwitch checked={enabled} onChange={onChange} bordered />
        </div>
    )
}

const SEVERITY_LEVELS = ['trace', 'debug', 'info', 'warn', 'error', 'fatal'] as const

interface LogsConfigFormProps {
    config: Record<string, any>
    onConfigChange: (config: Record<string, any>) => void
}

function LogsConfigForm({ config, onConfigChange }: LogsConfigFormProps): JSX.Element {
    const filters = config.filters || {}
    const selectedSeverities: string[] = filters.severityLevels || []
    const searchTerm: string = filters.searchTerm || ''
    const serviceNames: string[] = filters.serviceNames || []

    const updateFilters = (updates: Record<string, any>): void => {
        onConfigChange({
            ...config,
            filters: {
                ...filters,
                ...updates,
            },
        })
    }

    const toggleSeverity = (level: string): void => {
        const next = selectedSeverities.includes(level)
            ? selectedSeverities.filter((s) => s !== level)
            : [...selectedSeverities, level]
        updateFilters({ severityLevels: next.length > 0 ? next : undefined })
    }

    return (
        <div className="space-y-4">
            <div>
                <LemonLabel>Date range</LemonLabel>
                <LemonSelect
                    options={[
                        { value: '-1h', label: 'Last 1 hour' },
                        { value: '-24h', label: 'Last 24 hours' },
                        { value: '-7d', label: 'Last 7 days' },
                        { value: '-30d', label: 'Last 30 days' },
                    ]}
                    value={filters.dateFrom || '-24h'}
                    onChange={(value) => updateFilters({ dateFrom: value })}
                    fullWidth
                />
            </div>
            <div>
                <LemonLabel>Severity levels</LemonLabel>
                <p className="text-xs text-muted mb-2">Leave all unchecked to show all levels.</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                    {SEVERITY_LEVELS.map((level) => (
                        <LemonCheckbox
                            key={level}
                            checked={selectedSeverities.includes(level)}
                            onChange={() => toggleSeverity(level)}
                            label={level.charAt(0).toUpperCase() + level.slice(1)}
                        />
                    ))}
                </div>
            </div>

            <div>
                <LemonLabel>Search term</LemonLabel>
                <LemonInput
                    value={searchTerm}
                    onChange={(value) => updateFilters({ searchTerm: value || undefined })}
                    placeholder="Filter by log body text..."
                    fullWidth
                />
            </div>

            <div>
                <LemonLabel>Service names</LemonLabel>
                <p className="text-xs text-muted mb-1">Comma-separated list of service names to filter by.</p>
                <LemonInput
                    value={serviceNames.join(', ')}
                    onChange={(value) => {
                        const names = value
                            ? value
                                  .split(',')
                                  .map((s) => s.trim())
                                  .filter(Boolean)
                            : []
                        updateFilters({ serviceNames: names.length > 0 ? names : undefined })
                    }}
                    placeholder="e.g. api-server, worker, ingestion"
                    fullWidth
                />
            </div>
        </div>
    )
}

interface EntitySelectOption {
    value: number
    label: string
}

interface EntitySelectProps {
    endpoint: string
    value: number | undefined
    onChange: (value: number | undefined) => void
    placeholder: string
    searchPlaceholder: string
}

function EntitySelect({ endpoint, value, onChange, placeholder, searchPlaceholder }: EntitySelectProps): JSX.Element {
    const [allOptions, setAllOptions] = useState<EntitySelectOption[]>([])
    const [loading, setLoading] = useState(false)
    const [hasMore, setHasMore] = useState(false)
    const [searchTerm, setSearchTerm] = useState('')
    const nextUrlRef = useRef<string | null>(null)
    const [selectedLabel, setSelectedLabel] = useState<string | null>(null)

    // Fetch the currently selected entity so we always have its label
    useEffect(() => {
        if (value != null) {
            api.get(`${endpoint}/${value}`)
                .then((data: any) => setSelectedLabel(data.name || data.key || `#${data.id}`))
                .catch(() => {})
        }
    }, [endpoint, value])

    const fetchPage = useCallback(
        (url: string | null, append: boolean): void => {
            setLoading(true)
            const request = url ? api.get(url) : api.get(`${endpoint}/?limit=100`)
            request
                .then((data: any) => {
                    const newOptions: EntitySelectOption[] = (data.results || []).map((item: any) => ({
                        value: item.id,
                        label: item.name || item.key || `#${item.id}`,
                    }))
                    setAllOptions((prev) => (append ? [...prev, ...newOptions] : newOptions))
                    nextUrlRef.current = data.next || null
                    setHasMore(!!data.next)
                    setLoading(false)
                })
                .catch(() => setLoading(false))
        },
        [endpoint]
    )

    useEffect(() => {
        fetchPage(null, false)
    }, [fetchPage])

    useEffect(() => {
        if (hasMore && !loading) {
            fetchPage(nextUrlRef.current, true)
        }
    }, [hasMore, loading, fetchPage])

    // Ensure the selected value always has an option entry
    const optionsWithSelected = useMemo(() => {
        if (value == null || selectedLabel == null) {
            return allOptions
        }
        if (allOptions.some((o) => o.value === value)) {
            return allOptions
        }
        return [{ value, label: selectedLabel }, ...allOptions]
    }, [allOptions, value, selectedLabel])

    // Fuzzy-filter for the dropdown, but always keep the selected option for the button label
    const dropdownOptions = useMemo(() => {
        const searchInput: any = {
            label: () => (
                <LemonInput
                    type="search"
                    placeholder={searchPlaceholder}
                    autoFocus
                    value={searchTerm}
                    onChange={setSearchTerm}
                    fullWidth
                    onClick={(e: React.MouseEvent) => e.stopPropagation()}
                    className="mb-1"
                />
            ),
            custom: true,
        }

        if (!searchTerm) {
            return [searchInput, ...optionsWithSelected]
        }

        const fuse = new Fuse(optionsWithSelected, { keys: ['label'], threshold: 0.3 })
        const matched = fuse.search(searchTerm).map((r) => r.item)

        // Always include the currently selected option (hidden from search results but needed for button label)
        const selectedOption = value != null ? optionsWithSelected.find((o) => o.value === value) : null
        const filtered =
            selectedOption && !matched.some((o) => o.value === value)
                ? [...matched, { ...selectedOption, hidden: true } as any]
                : matched

        return [searchInput, ...filtered]
    }, [optionsWithSelected, searchTerm, searchPlaceholder, value])

    return (
        <LemonSelect
            options={dropdownOptions}
            value={value ?? null}
            onChange={(newValue) => {
                onChange(newValue ?? undefined)
                setSearchTerm('')
            }}
            placeholder={placeholder}
            loading={loading}
            fullWidth
        />
    )
}

interface WidgetConfigFormProps {
    widgetType: DashboardWidgetType
    config: Record<string, any>
    onConfigChange: (config: Record<string, any>) => void
}

export function WidgetConfigForm({ widgetType, config, onConfigChange }: WidgetConfigFormProps): JSX.Element {
    switch (widgetType) {
        case DashboardWidgetType.Experiment:
            return (
                <div className="space-y-4">
                    <div>
                        <LemonLabel>Experiment</LemonLabel>
                        <EntitySelect
                            endpoint="api/projects/@current/experiments"
                            value={config.experiment_id}
                            onChange={(value) => onConfigChange({ ...config, experiment_id: value })}
                            placeholder="Select an experiment..."
                            searchPlaceholder="Search experiments..."
                        />
                    </div>
                    <ControlsToggle
                        enabled={config.show_controls !== false}
                        onChange={(enabled) => onConfigChange({ ...config, show_controls: enabled })}
                        widgetType={widgetType}
                    />
                </div>
            )

        case DashboardWidgetType.SurveyResponses:
            return (
                <div className="space-y-4">
                    <div>
                        <LemonLabel>Survey</LemonLabel>
                        <EntitySelect
                            endpoint="api/projects/@current/surveys"
                            value={config.survey_id}
                            onChange={(value) => onConfigChange({ ...config, survey_id: value })}
                            placeholder="Select a survey..."
                            searchPlaceholder="Search surveys..."
                        />
                    </div>
                    <ControlsToggle
                        enabled={config.show_controls !== false}
                        onChange={(enabled) => onConfigChange({ ...config, show_controls: enabled })}
                        widgetType={widgetType}
                    />
                </div>
            )

        case DashboardWidgetType.FeatureFlag:
            return (
                <div className="space-y-4">
                    <div>
                        <LemonLabel>Feature flag</LemonLabel>
                        <EntitySelect
                            endpoint="api/projects/@current/feature_flags"
                            value={config.feature_flag_id}
                            onChange={(value) => onConfigChange({ ...config, feature_flag_id: value })}
                            placeholder="Select a feature flag..."
                            searchPlaceholder="Search flags..."
                        />
                    </div>
                    <ControlsToggle
                        enabled={config.show_controls !== false}
                        onChange={(enabled) => onConfigChange({ ...config, show_controls: enabled })}
                        widgetType={widgetType}
                    />
                </div>
            )

        case DashboardWidgetType.ErrorTracking:
            return (
                <div className="space-y-4">
                    <div>
                        <LemonLabel>Status filter</LemonLabel>
                        <LemonSelect
                            options={[
                                { value: '', label: 'All statuses' },
                                { value: 'active', label: 'Active' },
                                { value: 'resolved', label: 'Resolved' },
                                { value: 'pending_release', label: 'Pending release' },
                            ]}
                            value={config.status || ''}
                            onChange={(value) => onConfigChange({ ...config, status: value || undefined })}
                            fullWidth
                        />
                    </div>
                    <div>
                        <LemonLabel>Search</LemonLabel>
                        <LemonInput
                            value={config.search_query || ''}
                            onChange={(value) => onConfigChange({ ...config, search_query: value || undefined })}
                            placeholder="Filter by error name..."
                            fullWidth
                        />
                    </div>
                    <div>
                        <LemonLabel>Order by</LemonLabel>
                        <LemonSelect
                            options={[
                                { value: '-first_seen', label: 'Newest first' },
                                { value: 'first_seen', label: 'Oldest first' },
                                { value: '-created_at', label: 'Recently created' },
                            ]}
                            value={config.order_by || '-first_seen'}
                            onChange={(value) => onConfigChange({ ...config, order_by: value })}
                            fullWidth
                        />
                    </div>
                    <ControlsToggle
                        enabled={config.show_controls !== false}
                        onChange={(enabled) => onConfigChange({ ...config, show_controls: enabled })}
                        widgetType={widgetType}
                    />
                </div>
            )

        case DashboardWidgetType.Logs:
            return <LogsConfigForm config={config} onConfigChange={onConfigChange} />

        case DashboardWidgetType.SessionReplays:
            return (
                <div className="space-y-4">
                    <div>
                        <LemonLabel>Date range</LemonLabel>
                        <LemonSelect
                            options={[
                                { value: '-24h', label: 'Last 24 hours' },
                                { value: '-7d', label: 'Last 7 days' },
                                { value: '-30d', label: 'Last 30 days' },
                                { value: '-90d', label: 'Last 90 days' },
                            ]}
                            value={config.date_from || '-7d'}
                            onChange={(value) => onConfigChange({ ...config, date_from: value })}
                            fullWidth
                        />
                    </div>
                    <div>
                        <LemonLabel>Minimum duration</LemonLabel>
                        <LemonSelect
                            options={[
                                { value: 0, label: 'Any duration' },
                                { value: 10, label: 'At least 10 seconds' },
                                { value: 30, label: 'At least 30 seconds' },
                                { value: 60, label: 'At least 1 minute' },
                                { value: 300, label: 'At least 5 minutes' },
                            ]}
                            value={config.min_duration || 0}
                            onChange={(value) => onConfigChange({ ...config, min_duration: value || undefined })}
                            fullWidth
                        />
                    </div>
                </div>
            )

        default:
            return <></>
    }
}

/** Returns true if the given widget type requires entity selection before creation. */
export function widgetTypeRequiresConfig(widgetType: DashboardWidgetType): boolean {
    return (
        widgetType === DashboardWidgetType.Experiment ||
        widgetType === DashboardWidgetType.SurveyResponses ||
        widgetType === DashboardWidgetType.FeatureFlag
    )
}

/** Returns true if the config is valid for the given widget type. */
export function isWidgetConfigValid(widgetType: DashboardWidgetType, config: Record<string, any>): boolean {
    switch (widgetType) {
        case DashboardWidgetType.Experiment:
            return config.experiment_id != null
        case DashboardWidgetType.SurveyResponses:
            return config.survey_id != null
        case DashboardWidgetType.FeatureFlag:
            return config.feature_flag_id != null
        default:
            return true
    }
}
