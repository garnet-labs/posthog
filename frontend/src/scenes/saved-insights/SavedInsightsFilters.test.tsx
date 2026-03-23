import { MOCK_DEFAULT_BASIC_USER, MOCK_SECOND_BASIC_USER } from 'lib/api.mock'
import { useFeatureFlag } from 'lib/hooks/useFeatureFlag'

import '@testing-library/jest-dom'

import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'kea'

import { useMocks } from '~/mocks/jest'
import { initKeaTests } from '~/test/init'

import { SavedInsightsFilters } from './SavedInsightsFilters'
import { SavedInsightFilters, cleanFilters } from './savedInsightsLogic'

jest.mock('lib/hooks/useFeatureFlag', () => ({
    useFeatureFlag: jest.fn(),
}))

const DEFAULT_FILTERS: SavedInsightFilters = cleanFilters({})
const mockedUseFeatureFlag = useFeatureFlag as jest.MockedFunction<typeof useFeatureFlag>
const OUTLINE_HEART_PATH_PREFIX = 'M16.925 4.6'
const FILLED_HEART_PATH_PREFIX = 'M12.367 21.404'

describe('SavedInsightsFilters Created by dropdown', () => {
    let setFilters: jest.Mock

    beforeEach(() => {
        useMocks({
            get: {
                '/api/organizations/:organization_id/members/': {
                    results: [
                        {
                            id: '1',
                            user: MOCK_DEFAULT_BASIC_USER,
                            level: 8,
                            joined_at: '2020-09-24T15:05:26.758796Z',
                            updated_at: '2020-09-24T15:05:26.758837Z',
                            is_2fa_enabled: false,
                            has_social_auth: false,
                            last_login: '2020-09-24T15:05:26.758796Z',
                        },
                        {
                            id: '2',
                            user: MOCK_SECOND_BASIC_USER,
                            level: 1,
                            joined_at: '2021-03-11T19:11:11Z',
                            updated_at: '2021-03-11T19:11:11Z',
                            is_2fa_enabled: false,
                            has_social_auth: false,
                            last_login: '2021-03-11T19:11:11Z',
                        },
                    ],
                },
            },
        })
        initKeaTests()
        setFilters = jest.fn()
        mockedUseFeatureFlag.mockReturnValue(true)
    })

    afterEach(() => {
        cleanup()
    })

    function renderFilters(filters: Partial<SavedInsightFilters> = {}): void {
        render(
            <Provider>
                <SavedInsightsFilters filters={{ ...DEFAULT_FILTERS, ...filters }} setFilters={setFilters} />
            </Provider>
        )
    }

    it('loads and displays members when dropdown opens', async () => {
        renderFilters()
        await userEvent.click(screen.getByText('Created by'))

        await waitFor(() => {
            expect(screen.getByText('John')).toBeInTheDocument()
            expect(screen.getByText('Rose')).toBeInTheDocument()
        })
    })

    it('filters members by search term', async () => {
        renderFilters()
        await userEvent.click(screen.getByText('Created by'))

        await waitFor(() => {
            expect(screen.getByText('John')).toBeInTheDocument()
        })

        const overlay = screen.getByText('John').closest('.max-w-100')!
        const searchInput = within(overlay as HTMLElement).getByPlaceholderText('Search')
        await userEvent.type(searchInput, 'Rose')

        await waitFor(() => {
            expect(screen.getByText('Rose')).toBeInTheDocument()
            expect(screen.queryByText('John')).not.toBeInTheDocument()
        })
    })

    it('shows no matches for unrecognized search', async () => {
        renderFilters()
        await userEvent.click(screen.getByText('Created by'))

        await waitFor(() => {
            expect(screen.getByText('John')).toBeInTheDocument()
        })

        const overlay = screen.getByText('John').closest('.max-w-100')!
        const searchInput = within(overlay as HTMLElement).getByPlaceholderText('Search')
        await userEvent.type(searchInput, 'zzzzz')

        await waitFor(() => {
            expect(screen.getByText('No matches')).toBeInTheDocument()
        })
    })

    it('toggles member selection and calls setFilters', async () => {
        renderFilters()
        await userEvent.click(screen.getByText('Created by'))

        await waitFor(() => {
            expect(screen.getByText('Rose')).toBeInTheDocument()
        })

        await userEvent.click(screen.getByText('Rose'))

        expect(setFilters).toHaveBeenCalledWith({ createdBy: [MOCK_SECOND_BASIC_USER.id] })
    })

    it('renders the outlined heart icon when favorites filter is disabled', () => {
        renderFilters({ favorited: false })

        const favoritesIconPath = screen.getByRole('button', { name: 'Favorites' }).querySelector('svg path')

        expect(favoritesIconPath?.getAttribute('d')).toContain(OUTLINE_HEART_PATH_PREFIX)
    })

    it('renders the filled heart icon when favorites filter is enabled', () => {
        renderFilters({ favorited: true })

        const favoritesIconPath = screen.getByRole('button', { name: 'Favorites' }).querySelector('svg path')

        expect(favoritesIconPath?.getAttribute('d')).toContain(FILLED_HEART_PATH_PREFIX)
    })
})
