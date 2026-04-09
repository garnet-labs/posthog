import { alignResolvedDateRangeToInterval } from './InsightDateFilter'

describe('alignResolvedDateRangeToInterval', () => {
    it('returns undefined when resolvedDateRange is missing', () => {
        expect(alignResolvedDateRangeToInterval(undefined, 'month')).toBeUndefined()
        expect(alignResolvedDateRangeToInterval(null, 'month')).toBeUndefined()
    })

    it('returns the range unchanged when grouping by day', () => {
        const range = {
            date_from: '2025-04-07T00:00:00+00:00',
            date_to: '2026-04-07T23:59:59+00:00',
        }
        expect(alignResolvedDateRangeToInterval(range, 'day')).toBe(range)
    })

    it('returns the range unchanged when interval is missing', () => {
        const range = {
            date_from: '2025-04-07T00:00:00+00:00',
            date_to: '2026-04-07T23:59:59+00:00',
        }
        expect(alignResolvedDateRangeToInterval(range, null)).toBe(range)
    })

    it('expands to full months when grouping by month', () => {
        expect(
            alignResolvedDateRangeToInterval(
                {
                    date_from: '2025-04-07T00:00:00+00:00',
                    date_to: '2026-04-07T23:59:59+00:00',
                },
                'month'
            )
        ).toEqual({
            date_from: '2025-04-01T00:00:00+00:00',
            date_to: '2026-04-30T23:59:59+00:00',
        })
    })

    it('preserves a non-UTC timezone offset', () => {
        expect(
            alignResolvedDateRangeToInterval(
                {
                    date_from: '2025-04-07T00:00:00-08:00',
                    date_to: '2026-04-07T23:59:59-08:00',
                },
                'month'
            )
        ).toEqual({
            date_from: '2025-04-01T00:00:00-08:00',
            date_to: '2026-04-30T23:59:59-08:00',
        })
    })
})
