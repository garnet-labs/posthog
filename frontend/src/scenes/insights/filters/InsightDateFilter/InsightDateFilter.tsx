import { useActions, useValues } from 'kea'

import { IconCalendar } from '@posthog/icons'

import { DateFilter } from 'lib/components/DateFilter/DateFilter'
import { dateMapping } from 'lib/utils'
import { insightLogic } from 'scenes/insights/insightLogic'
import { insightVizDataLogic } from 'scenes/insights/insightVizDataLogic'

import { ResolvedDateRangeResponse } from '~/queries/schema/schema-general'
import { IntervalType } from '~/types'

type InsightDateFilterProps = {
    disabled: boolean
}

const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

const isLeapYear = (year: number): boolean => (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0

const daysInMonth = (year: number, month: number): number =>
    month === 2 && isLeapYear(year) ? 29 : DAYS_IN_MONTH[month - 1]

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
    // ISO input like "2025-04-07T00:00:00+00:00" — just swap the day + time parts and
    // keep the original timezone suffix so we stay in the same wall-clock tz.
    const clampToMonth = (iso: string, boundary: 'start' | 'end'): string => {
        const ymd = iso.slice(0, 7) // "YYYY-MM"
        const tz = iso.slice(19) // everything after "YYYY-MM-DDTHH:mm:ss"
        if (boundary === 'start') {
            return `${ymd}-01T00:00:00${tz}`
        }
        const [year, month] = ymd.split('-').map(Number)
        const lastDay = String(daysInMonth(year, month)).padStart(2, '0')
        return `${ymd}-${lastDay}T23:59:59${tz}`
    }
    return {
        date_from: clampToMonth(resolvedDateRange.date_from, 'start'),
        date_to: clampToMonth(resolvedDateRange.date_to, 'end'),
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
