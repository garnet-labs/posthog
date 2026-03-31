import '@testing-library/jest-dom'

import { cleanup, render, screen } from '@testing-library/react'

import { OccurrencesList } from './OccurrencesList'

const DAY = 86400000

describe('OccurrencesList', () => {
    afterEach(() => {
        cleanup()
    })

    it('shows "No upcoming occurrences" when all dates are in the past', () => {
        const past = [new Date(Date.now() - DAY), new Date(Date.now() - DAY * 2)]
        render(<OccurrencesList occurrences={past} isFinite={true} />)
        expect(screen.getByText('No upcoming occurrences')).toBeInTheDocument()
    })

    it('shows "No upcoming occurrences" when occurrences array is empty', () => {
        render(<OccurrencesList occurrences={[]} isFinite={true} />)
        expect(screen.getByText('No upcoming occurrences')).toBeInTheDocument()
    })

    it('renders future occurrences with correct formatting', () => {
        const future = [new Date(Date.now() + DAY), new Date(Date.now() + DAY * 2)]
        const { container } = render(<OccurrencesList occurrences={future} isFinite={true} />)
        const rows = container.querySelectorAll('.flex.items-center.justify-between')
        expect(rows).toHaveLength(2)
    })

    it('gives the first occurrence a "next" tag', () => {
        const future = [new Date(Date.now() + DAY), new Date(Date.now() + DAY * 2)]
        render(<OccurrencesList occurrences={future} isFinite={true} />)
        expect(screen.getByText('next')).toBeInTheDocument()
    })

    it('gives the last occurrence a "last" tag in a finite list', () => {
        const future = [new Date(Date.now() + DAY), new Date(Date.now() + DAY * 2)]
        render(<OccurrencesList occurrences={future} isFinite={true} />)
        expect(screen.getByText('last')).toBeInTheDocument()
    })

    it('collapses long lists showing head + "...N more..." + tail', () => {
        const future = Array.from({ length: 10 }, (_, i) => new Date(Date.now() + DAY * (i + 1)))
        render(<OccurrencesList occurrences={future} isFinite={true} />)

        // VISIBLE_HEAD=4, VISIBLE_TAIL=1, hidden = 10 - 4 - 1 = 5
        expect(screen.getByText('...5 more occurrences...')).toBeInTheDocument()

        // Only head + tail rows rendered (not all 10)
        const rows = document.querySelectorAll('.flex.items-center.justify-between')
        expect(rows).toHaveLength(5) // 4 head + 1 tail
    })

    it('shows "...continues indefinitely" for non-finite lists', () => {
        const future = [new Date(Date.now() + DAY), new Date(Date.now() + DAY * 2)]
        render(<OccurrencesList occurrences={future} isFinite={false} />)
        expect(screen.getByText('...continues indefinitely')).toBeInTheDocument()
    })

    it('filters out past occurrences and only renders future ones', () => {
        const mixed = [
            new Date(Date.now() - DAY * 2),
            new Date(Date.now() - DAY),
            new Date(Date.now() + DAY),
            new Date(Date.now() + DAY * 2),
        ]
        const { container } = render(<OccurrencesList occurrences={mixed} isFinite={true} />)
        const rows = container.querySelectorAll('.flex.items-center.justify-between')
        expect(rows).toHaveLength(2)
    })
})
