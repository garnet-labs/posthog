import { useActions, useValues } from 'kea'

import { IconCalendar } from '@posthog/icons'
import { LemonSwitch } from '@posthog/lemon-ui'

import { DateFilter } from 'lib/components/DateFilter/DateFilter'
import { Tooltip } from 'lib/lemon-ui/Tooltip'
import { dateMapping } from 'lib/utils'
import { insightLogic } from 'scenes/insights/insightLogic'
import { insightVizDataLogic } from 'scenes/insights/insightVizDataLogic'

type InsightDateFilterProps = {
    disabled: boolean
}

export function InsightDateFilter({ disabled }: InsightDateFilterProps): JSX.Element {
    const { insightProps, editingDisabledReason } = useValues(insightLogic)
    const { isTrends, dateRange } = useValues(insightVizDataLogic(insightProps))
    const { updateDateRange } = useActions(insightVizDataLogic(insightProps))
    const { insightData } = useValues(insightVizDataLogic(insightProps))

    const isRollingDateRange = !dateRange?.date_to
    const showIncompleteDataToggle = isTrends && isRollingDateRange

    return (
        <div className="flex items-center gap-2">
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
                allowedRollingDateOptions={isTrends ? ['hours', 'days', 'weeks', 'months', 'years'] : undefined}
                resolvedDateRange={insightData?.resolved_date_range}
                makeLabel={(key) => (
                    <>
                        <IconCalendar /> {key}
                    </>
                )}
            />
            {showIncompleteDataToggle && (
                <Tooltip title="Show data for the current incomplete time period (e.g. today when viewing by day)">
                    <span>
                        <LemonSwitch
                            label="Incomplete data"
                            checked={dateRange?.hideIncompleteData === false}
                            onChange={(checked) => {
                                updateDateRange({ hideIncompleteData: !checked }, true)
                            }}
                            size="small"
                            disabled={disabled}
                        />
                    </span>
                </Tooltip>
            )}
        </div>
    )
}
