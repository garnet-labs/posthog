export interface SystemTableDefaults {
    timestamp_field: string
    id_field: string
}

const SYSTEM_TABLE_DEFAULT_FIELDS: Record<string, SystemTableDefaults | null> = {
    'system.actions': { timestamp_field: 'created_at', id_field: 'id' },
    'system.cohort_calculation_history': { timestamp_field: 'started_at', id_field: 'id' },
    'system.cohorts': { timestamp_field: 'created_at', id_field: 'id' },
    'system.dashboards': { timestamp_field: 'created_at', id_field: 'id' },
    'system.data_warehouse_sources': { timestamp_field: 'created_at', id_field: 'id' },
    'system.data_warehouse_tables': { timestamp_field: 'created_at', id_field: 'id' },
    'system.error_tracking_issues': { timestamp_field: 'created_at', id_field: 'id' },
    'system.experiments': { timestamp_field: 'created_at', id_field: 'id' },
    'system.exports': { timestamp_field: 'created_at', id_field: 'id' },
    'system.feature_flags': { timestamp_field: 'created_at', id_field: 'id' },
    'system.groups': { timestamp_field: 'created_at', id_field: 'id' },
    'system.group_type_mappings': null, // no timestamp fields
    'system.hog_flows': { timestamp_field: 'created_at', id_field: 'id' },
    'system.hog_functions': { timestamp_field: 'created_at', id_field: 'id' },
    'system.ingestion_warnings': null, // no id field
    'system.insight_variables': null, // no timestamp fields
    'system.insights': { timestamp_field: 'created_at', id_field: 'id' },
    'system.notebooks': { timestamp_field: 'created_at', id_field: 'id' },
    'system.surveys': { timestamp_field: 'created_at', id_field: 'id' },
    'system.teams': { timestamp_field: 'created_at', id_field: 'id' },
}

export function getSystemTableDefaults(tableName: string): SystemTableDefaults | null {
    return SYSTEM_TABLE_DEFAULT_FIELDS[tableName] ?? null
}

export function isUsableSystemTable(tableName: string): boolean {
    return getSystemTableDefaults(tableName) !== null
}
