import { actions, kea, listeners, path, reducers, selectors } from 'kea'
import { loaders } from 'kea-loaders'

import { toolbarFetch } from '~/toolbar/toolbarConfigLogic'
import { Survey } from '~/types'

import type { surveysToolbarLogicType } from './surveysToolbarLogicType'

export type SurveyStatus = 'draft' | 'active' | 'stopped' | 'complete'

export function getSurveyStatus(survey: Survey): SurveyStatus {
    if (!survey.start_date) {
        return 'draft'
    }
    if (survey.end_date) {
        return 'complete'
    }
    if (survey.archived) {
        return 'stopped'
    }
    return 'active'
}

export const surveysToolbarLogic = kea<surveysToolbarLogicType>([
    path(['toolbar', 'surveys', 'surveysToolbarLogic']),

    actions({
        setSearchTerm: (searchTerm: string) => ({ searchTerm }),
        debouncedSearch: true,
        showButtonSurveys: true,
        hideButtonSurveys: true,
    }),

    loaders(({ values }) => ({
        allSurveys: [
            [] as Survey[],
            {
                loadSurveys: async () => {
                    const params = new URLSearchParams()
                    if (values.searchTerm) {
                        params.set('search', values.searchTerm)
                    }
                    const url = `/api/projects/@current/surveys/${params.toString() ? `?${params}` : ''}`
                    const response = await toolbarFetch(url)
                    if (!response.ok) {
                        return []
                    }
                    const data = await response.json()
                    const surveys: Survey[] = data.results ?? data
                    return surveys.filter((s) => !s.archived)
                },
            },
        ],
    })),

    reducers({
        searchTerm: [
            '',
            {
                setSearchTerm: (_, { searchTerm }) => searchTerm,
            },
        ],
    }),

    selectors({
        filteredSurveys: [(s) => [s.allSurveys], (allSurveys): Survey[] => allSurveys],
    }),

    listeners(({ actions }) => ({
        setSearchTerm: async (_, breakpoint) => {
            await breakpoint(300)
            actions.loadSurveys()
        },
    })),
])
