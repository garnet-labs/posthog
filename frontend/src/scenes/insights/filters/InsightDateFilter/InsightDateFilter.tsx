import { useActions, useValues } from 'kea'

import { IconCalendar } from '@posthog/icons'

import { DateFilter } from 'lib/components/DateFilter/DateFilter'
import { dayjs } from 'lib/dayjs'
import { dateMapping } from 'lib/utils'
import { insightLogic } from 'scenes/insights/insightLogic'
import { insightVizDataLogic } from 'scenes/insights/insightVizDataLogic'

import { ResolvedDateRangeResponse } from '~/queries/schema/schema-general'
import { IntervalType } from '~/types'

type InsightDateFilterProps = {
    disabled: boolean
}

// When an insight is grouped by month, the query's WHERE clause uses
// toStartOfInterval(date_from, month), so the first and last chart buckets cover the
// whole month. Expand the resolved range we show in the tooltip to match — otherwise
// "Last 12 months" from April 7 looks like it excludes April 1–6, which it doesn't.
export function alignResolvedDateRangeToInterval(
    resolvedDateRange: ResolvedDateRangeResponse | null | undefined,
    interval: IntervalType | null | undefined
): ResolvedDateRangeResponse | undefined {
    if (!resolvedDateRange?.date_from || !resolvedDateRange?.date_to) {
        return resolvedDateRange ?? undefined
    }
    if (interval !== 'month') {
        return resolvedDateRange
    }
    // Parse the wall-clock portion only, so manipulation stays in the original tz.
    const stripTz = (iso: string): string => iso.replace(/([+-]\d{2}:\d{2}|Z)$/, '')
    const tzSuffix = (iso: string): string => (iso.endsWith('Z') ? '+00:00' : iso.slice(-6))
    const from = dayjs.utc(stripTz(resolvedDateRange.date_from)).startOf('month')
    const to = dayjs.utc(stripTz(resolvedDateRange.date_to)).endOf('month')
    return {
        date_from: from.format('YYYY-MM-DDTHH:mm:ss') + tzSuffix(resolvedDateRange.date_from),
        date_to: to.format('YYYY-MM-DDTHH:mm:ss') + tzSuffix(resolvedDateRange.date_to),
    }
}

export function InsightDateFilter({ disabled }: InsightDateFilterProps): JSX.Element {
    const { insightProps, editingDisabledReason } = useValues(insightLogic)
    const { dateRange, interval } = useValues(insightVizDataLogic(insightProps))
    const { updateDateRange } = useActions(insightVizDataLogic(insightProps))
    const { insightData } = useValues(insightVizDataLogic(insightProps))

    return (
        <DateFilter
            showExplicitDateToggle
            dateTo={dateRange?.date_to ?? undefined}
            dateFrom={dateRange?.date_from ?? '-7d'}
            explicitDate={dateRange?.explicitDate ?? false}
            allowTimePrecision
            allowFixedRangeWithTime
            disabled={disabled}
            disabledReason={editingDisabledReason}
            onChange={(date_from, date_to, explicit_date) => {
                // Prevent debouncing when toggling the exact time range toggle as it glitches the animation
                const ignoreDebounce = dateRange?.explicitDate !== explicit_date
                updateDateRange({ date_from, date_to, explicitDate: explicit_date }, ignoreDebounce)
            }}
            dateOptions={dateMapping}
            allowedRollingDateOptions={['hours', 'days', 'weeks', 'months', 'years']}
            resolvedDateRange={alignResolvedDateRangeToInterval(insightData?.resolved_date_range, interval)}
            makeLabel={(key) => (
                <>
                    <IconCalendar /> {key}
                </>
            )}
        />
    )
}
