import { sortFilesByModifiedAt } from './hogbotResearchLogic'

describe('sortFilesByModifiedAt', () => {
    it('orders research files by latest modified timestamp first', () => {
        const files = [
            {
                path: '/research/oldest.md',
                filename: 'oldest.md',
                size: 100,
                modified_at: '2026-03-24T08:00:00Z',
            },
            {
                path: '/research/newest.md',
                filename: 'newest.md',
                size: 200,
                modified_at: '2026-03-25T10:30:00Z',
            },
            {
                path: '/research/middle.md',
                filename: 'middle.md',
                size: 150,
                modified_at: '2026-03-25T10:01:30Z',
            },
        ]

        expect(sortFilesByModifiedAt(files).map((file) => file.path)).toEqual([
            '/research/newest.md',
            '/research/middle.md',
            '/research/oldest.md',
        ])
    })

    it('pushes invalid timestamps to the end', () => {
        const files = [
            {
                path: '/research/unknown.md',
                filename: 'unknown.md',
                size: 100,
                modified_at: 'not-a-date',
            },
            {
                path: '/research/known.md',
                filename: 'known.md',
                size: 200,
                modified_at: '2026-03-25T10:30:00Z',
            },
        ]

        expect(sortFilesByModifiedAt(files).map((file) => file.path)).toEqual([
            '/research/known.md',
            '/research/unknown.md',
        ])
    })
})
