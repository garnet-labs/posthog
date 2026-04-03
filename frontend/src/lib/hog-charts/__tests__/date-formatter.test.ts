import { createXAxisTickCallback, inferInterval, parseDateForAxis } from '../core/date-formatter'

function weeklyDates(start: string, count: number): string[] {
    const dates: string[] = []
    const d = new Date(start + 'T00:00:00Z')
    for (let i = 0; i < count; i++) {
        dates.push(d.toISOString().slice(0, 10))
        d.setDate(d.getDate() + 7)
    }
    return dates
}

function hourlyDates(start: string, count: number): string[] {
    return Array.from({ length: count }, (_, i) => {
        const d = new Date(Date.UTC(+start.slice(0, 4), +start.slice(5, 7) - 1, +start.slice(8, 10), i))
        return d.toISOString().replace('T', ' ').slice(0, 19)
    })
}

function sparseLabels(length: number, labels: Record<number, string>): (string | null)[] {
    return Array.from({ length }, (_, i) => labels[i] ?? null)
}

describe('hog-charts date-formatter', () => {
    describe('inferInterval', () => {
        it.each([
            { desc: 'single date defaults to day', dates: ['2025-04-01'], expected: 'day' },
            {
                desc: 'sub-hour gaps → minute',
                dates: ['2025-04-01 10:00:00', '2025-04-01 10:01:00'],
                expected: 'minute',
            },
            { desc: '1 hour gaps → hour', dates: ['2025-04-01 10:00:00', '2025-04-01 11:00:00'], expected: 'hour' },
            { desc: '1 day gaps → day', dates: ['2025-04-01', '2025-04-02'], expected: 'day' },
            { desc: '7 day gaps → week', dates: ['2025-04-07', '2025-04-14'], expected: 'week' },
            { desc: '~30 day gaps → month', dates: ['2025-01-01', '2025-02-01'], expected: 'month' },
        ])('$desc', ({ dates, expected }) => {
            const parsed = dates.map((d) => parseDateForAxis(d, 'UTC'))
            expect(inferInterval(parsed)).toBe(expected)
        })
    })

    describe('parseDateForAxis', () => {
        it.each([
            { desc: 'date-only string', input: '2025-04-01', timezone: 'UTC', expectedMonth: 3, expectedHour: 0 },
            {
                desc: 'datetime string',
                input: '2025-04-01 14:30:00',
                timezone: 'UTC',
                expectedMonth: 3,
                expectedHour: 14,
            },
            {
                desc: 'ISO datetime with T',
                input: '2025-04-01T14:30:00',
                timezone: 'UTC',
                expectedMonth: 3,
                expectedHour: 14,
            },
        ])('parses $desc', ({ input, timezone, expectedMonth, expectedHour }) => {
            const result = parseDateForAxis(input, timezone)
            expect(result.isValid()).toBe(true)
            expect(result.month()).toBe(expectedMonth)
            expect(result.hour()).toBe(expectedHour)
        })

        it('returns an invalid dayjs for unparseable input', () => {
            expect(parseDateForAxis('not-a-date', 'UTC').isValid()).toBe(false)
        })

        it('preserves wall-clock digits in non-UTC timezone', () => {
            const result = parseDateForAxis('2025-04-01 14:00:00', 'America/New_York')
            expect(result.isValid()).toBe(true)
            expect(result.hour()).toBe(14)
        })
    })

    describe('createXAxisTickCallback', () => {
        describe.each([
            {
                scenario: 'monthly → year at Jan, full month names otherwise',
                interval: 'month' as const,
                allDays: ['2025-01-01', '2025-02-01', '2025-03-01', '2025-04-01'],
                expected: ['2025', 'February', 'March', 'April'],
            },
            {
                scenario: 'monthly cross-year → year at January boundary',
                interval: 'month' as const,
                allDays: ['2025-11-01', '2025-12-01', '2026-01-01', '2026-02-01'],
                expected: ['November', 'December', '2026', 'February'],
            },
            {
                scenario: 'daily short span → full month name on 1st, MMM D otherwise',
                interval: 'day' as const,
                allDays: ['2025-04-28', '2025-04-29', '2025-04-30', '2025-05-01', '2025-05-02'],
                expected: ['Apr 28', 'Apr 29', 'Apr 30', 'May', 'May 2'],
            },
            {
                scenario: 'daily crossing Jan 1 → year on 1st',
                interval: 'day' as const,
                allDays: ['2025-12-30', '2025-12-31', '2026-01-01', '2026-01-02'],
                expected: ['Dec 30', 'Dec 31', '2026', 'Jan 2'],
            },
            {
                scenario: 'weekly short span → MMM D',
                interval: 'week' as const,
                allDays: ['2025-04-07', '2025-04-14', '2025-04-21'],
                expected: ['Apr 7', 'Apr 14', 'Apr 21'],
            },
            {
                scenario: 'weekly long span → monthly labels at boundaries',
                interval: 'week' as const,
                allDays: weeklyDates('2025-09-01', 18),
                expected: sparseLabels(18, {
                    0: 'September',
                    5: 'October',
                    9: 'November',
                    13: 'December',
                }),
            },
            {
                scenario: 'hourly single day → HH:mm',
                interval: 'hour' as const,
                allDays: ['2025-04-01 14:00:00', '2025-04-01 15:00:00', '2025-04-01 16:00:00'],
                expected: ['14:00', '15:00', '16:00'],
            },
            {
                scenario: 'minute → HH:mm',
                interval: 'minute' as const,
                allDays: ['2025-04-01 14:30:00', '2025-04-01 14:31:00', '2025-04-01 14:32:00'],
                expected: ['14:30', '14:31', '14:32'],
            },
            {
                scenario: 'second → treated as hourly (HH:mm)',
                interval: 'second' as const,
                allDays: ['2025-04-01 14:30:00', '2025-04-01 14:30:01', '2025-04-01 14:30:02'],
                expected: ['14:30', '14:30', '14:30'],
            },
            {
                scenario: 'hourly multi-day (3 days) → date at day start, HH:mm every 6h',
                interval: 'hour' as const,
                allDays: hourlyDates('2025-02-15', 72),
                expected: sparseLabels(72, {
                    0: 'Feb 15',
                    6: '06:00',
                    12: '12:00',
                    18: '18:00',
                    24: 'Feb 16',
                    30: '06:00',
                    36: '12:00',
                    42: '18:00',
                    48: 'Feb 17',
                    54: '06:00',
                    60: '12:00',
                    66: '18:00',
                }),
            },
            {
                scenario: 'hourly multi-day (4 days) → day-start labels only',
                interval: 'hour' as const,
                allDays: hourlyDates('2025-02-15', 96),
                expected: sparseLabels(96, {
                    0: 'Feb 15',
                    24: 'Feb 16',
                    48: 'Feb 17',
                    72: 'Feb 18',
                }),
            },
            {
                scenario: 'inferred month from ~30 day gaps',
                interval: undefined,
                allDays: ['2025-01-01', '2025-02-01', '2025-03-01'],
                expected: ['2025', 'February', 'March'],
            },
            {
                scenario: 'inferred day from 1 day gaps',
                interval: undefined,
                allDays: ['2025-04-01', '2025-04-02', '2025-04-03'],
                expected: ['April', 'Apr 2', 'Apr 3'],
            },
            {
                scenario: 'inferred hour from 1 hour gaps',
                interval: undefined,
                allDays: ['2025-04-01 10:00:00', '2025-04-01 11:00:00', '2025-04-01 12:00:00'],
                expected: ['10:00', '11:00', '12:00'],
            },
        ])('$scenario', ({ interval, allDays, expected }) => {
            const callback = createXAxisTickCallback({ interval, allDays, timezone: 'UTC' })

            it.each(expected.map((exp, i) => ({ index: i, expected: exp })))(
                'formats index $index as $expected',
                ({ index, expected: exp }) => {
                    expect(callback('ignored', index)).toBe(exp)
                }
            )
        })

        describe('non-UTC timezone', () => {
            it('does not shift hour labels because datetime strings are already in project timezone', () => {
                const callback = createXAxisTickCallback({
                    interval: 'hour',
                    allDays: ['2025-04-01 00:00:00', '2025-04-01 01:00:00', '2025-04-01 02:00:00'],
                    timezone: 'America/New_York',
                })
                expect(callback('ignored', 0)).toBe('00:00')
                expect(callback('ignored', 1)).toBe('01:00')
                expect(callback('ignored', 2)).toBe('02:00')
            })

            it.each([
                { interval: 'month' as const, desc: 'month interval' },
                { interval: 'day' as const, desc: 'day interval' },
                { interval: undefined, desc: 'inferred interval' },
            ])('does not shift month labels across month boundaries ($desc)', ({ interval }) => {
                const callback = createXAxisTickCallback({
                    interval,
                    allDays: ['2023-06-01', '2023-07-01', '2023-08-01'],
                    timezone: 'US/Pacific',
                })
                expect(callback('ignored', 0)).toBe('June')
                expect(callback('ignored', 1)).toBe('July')
                expect(callback('ignored', 2)).toBe('August')
            })
        })

        describe('fallbacks', () => {
            it.each([
                {
                    desc: 'empty allDays returns raw value',
                    args: { interval: 'day' as const, allDays: [] as string[], timezone: 'UTC' },
                    input: '2025-04-01',
                    index: 0,
                    expected: '2025-04-01',
                },
                {
                    desc: 'out-of-bounds index returns raw value',
                    args: { interval: 'day' as const, allDays: ['2025-04-01'], timezone: 'UTC' },
                    input: 'some-label',
                    index: 5,
                    expected: 'some-label',
                },
                {
                    desc: 'numeric allDays returns stringified value',
                    args: { interval: 'day' as const, allDays: [1, 2, 3] as any[], timezone: 'UTC' },
                    input: 1,
                    index: 0,
                    expected: '1',
                },
                {
                    desc: 'unparseable dates return raw value',
                    args: { interval: 'day' as const, allDays: ['not-a-date'], timezone: 'UTC' },
                    input: 'fallback',
                    index: 0,
                    expected: 'fallback',
                },
            ])('$desc', ({ args, input, index, expected }) => {
                const callback = createXAxisTickCallback(args)
                expect(callback(input, index)).toBe(expected)
            })
        })
    })
})
