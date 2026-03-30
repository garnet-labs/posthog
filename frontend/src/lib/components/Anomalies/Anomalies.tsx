import { useActions, useValues } from 'kea'

import { IconSparkles } from '@posthog/icons'

import { DetectiveHog } from 'lib/components/hedgehogs'
import { ProductIntroduction } from 'lib/components/ProductIntroduction/ProductIntroduction'
import { TZLabel } from 'lib/components/TZLabel'
import { LemonInput } from 'lib/lemon-ui/LemonInput'
import { LemonSegmentedButton } from 'lib/lemon-ui/LemonSegmentedButton'
import { LemonSelect } from 'lib/lemon-ui/LemonSelect'
import { LemonTable, LemonTableColumns } from 'lib/lemon-ui/LemonTable'
import { LemonTableLink } from 'lib/lemon-ui/LemonTable/LemonTableLink'
import { LemonTag } from 'lib/lemon-ui/LemonTag'
import { urls } from 'scenes/urls'

import { ProductKey } from '~/queries/schema/schema-general'
import { InsightShortId } from '~/types'

import { anomaliesLogic } from './anomaliesLogic'
import { AnomalySparkline } from './AnomalySparkline'
import { AnomalyInterval, AnomalyScoreType, AnomalyWindow } from './types'

function scoreColor(score: number): 'danger' | 'warning' | 'muted' {
    if (score >= 0.95) {
        return 'danger'
    }
    if (score >= 0.9) {
        return 'warning'
    }
    return 'muted'
}

function intervalLabel(interval: string): string {
    switch (interval) {
        case 'hour':
            return 'Hourly'
        case 'day':
            return 'Daily'
        case 'week':
            return 'Weekly'
        case 'month':
            return 'Monthly'
        default:
            return interval
    }
}

export function Anomalies(): JSX.Element {
    const { filteredAnomalies, anomaliesLoading, window, search, intervalFilter } = useValues(anomaliesLogic)
    const { setWindow, setSearch, setIntervalFilter } = useActions(anomaliesLogic)

    const columns: LemonTableColumns<AnomalyScoreType> = [
        {
            title: 'Score',
            dataIndex: 'score',
            width: 80,
            sorter: (a, b) => a.score - b.score,
            render: function renderScore(_, anomaly) {
                return (
                    <LemonTag type={scoreColor(anomaly.score)} size="small">
                        {Math.round(anomaly.score * 100)}%
                    </LemonTag>
                )
            },
        },
        {
            title: 'Insight',
            key: 'insight',
            render: function renderInsight(_, anomaly) {
                return (
                    <LemonTableLink
                        to={urls.insightView(anomaly.insight_short_id as InsightShortId)}
                        title={anomaly.insight_name}
                        description={anomaly.series_label !== anomaly.insight_name ? anomaly.series_label : undefined}
                    />
                )
            },
        },
        {
            title: 'Sparkline',
            key: 'sparkline',
            width: 140,
            render: function renderSparkline(_, anomaly) {
                if (!anomaly.data_snapshot?.data?.length) {
                    return <span className="text-muted">No data</span>
                }
                return <AnomalySparkline anomaly={anomaly} />
            },
        },
        {
            title: 'When',
            dataIndex: 'timestamp',
            sorter: (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
            render: function renderTimestamp(timestamp: any) {
                return <div className="whitespace-nowrap">{timestamp && <TZLabel time={timestamp} />}</div>
            },
        },
        {
            title: 'Interval',
            dataIndex: 'interval',
            width: 90,
            render: function renderInterval(interval: any) {
                return (
                    <LemonTag type="muted" size="small">
                        {intervalLabel(interval)}
                    </LemonTag>
                )
            },
        },
    ]

    return (
        <div className="space-y-4">
            {filteredAnomalies.length === 0 && !anomaliesLoading ? (
                <ProductIntroduction
                    productName="Anomalies"
                    productKey={ProductKey.PRODUCT_ANALYTICS}
                    thingName="anomaly"
                    description="Anomaly detection automatically monitors your time-series insights and surfaces unusual metrics. Anomalies will appear here once the scoring pipeline has processed your recently viewed insights."
                    isEmpty={true}
                    customHog={DetectiveHog}
                />
            ) : (
                <>
                    <div className="flex items-center gap-3 flex-wrap">
                        <LemonSelect
                            size="small"
                            value={window}
                            onChange={(value) => setWindow(value as AnomalyWindow)}
                            options={[
                                { value: '24h', label: 'Last 24 hours' },
                                { value: '7d', label: 'Last 7 days' },
                                { value: '30d', label: 'Last 30 days' },
                            ]}
                        />
                        <LemonSegmentedButton
                            size="small"
                            value={intervalFilter}
                            onChange={(value) => setIntervalFilter(value as AnomalyInterval)}
                            options={[
                                { value: '', label: 'All' },
                                { value: 'hour', label: 'Hourly' },
                                { value: 'day', label: 'Daily' },
                                { value: 'week', label: 'Weekly' },
                                { value: 'month', label: 'Monthly' },
                            ]}
                        />
                        <LemonInput
                            type="search"
                            size="small"
                            placeholder="Search insights..."
                            value={search}
                            onChange={setSearch}
                            className="max-w-60"
                        />
                        <div className="flex items-center gap-1 text-muted text-xs ml-auto">
                            <IconSparkles className="text-warning" />
                            {filteredAnomalies.length} anomal{filteredAnomalies.length === 1 ? 'y' : 'ies'} found
                        </div>
                    </div>
                    <LemonTable
                        loading={anomaliesLoading}
                        columns={columns}
                        dataSource={filteredAnomalies}
                        rowKey="id"
                        pagination={{ pageSize: 20 }}
                        noSortingCancellation
                        defaultSorting={{ columnKey: 'score', order: -1 }}
                        emptyState="No anomalies found for the selected filters."
                    />
                </>
            )}
        </div>
    )
}
