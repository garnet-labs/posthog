export interface AnomalyScoreType {
    id: string
    insight_id: number
    insight_name: string
    insight_short_id: string
    series_index: number
    series_label: string
    timestamp: string
    score: number
    is_anomalous: boolean
    interval: string
    data_snapshot: {
        data: number[]
        dates: string[]
        anomaly_index: number | null
    }
    scored_at: string
}

export type AnomalyWindow = '24h' | '7d' | '30d'
export type AnomalyInterval = '' | 'hour' | 'day' | 'week' | 'month'
