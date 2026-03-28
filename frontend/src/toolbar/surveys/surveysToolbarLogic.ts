import Fuse from 'fuse.js'
import { actions, kea, path, reducers, selectors } from 'kea'
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
        showButtonSurveys: true,
        hideButtonSurveys: true,
    }),

    loaders(() => ({
        allSurveys: [
            [] as Survey[],
            {
                loadSurveys: async () => {
                    const response = await toolbarFetch('/api/projects/@current/surveys/')
                    if (!response.ok) {
                        return []
                    }
                    const data = await response.json()
                    return data.results ?? data
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
        filteredSurveys: [
            (s) => [s.searchTerm, s.allSurveys],
            (searchTerm, allSurveys): Survey[] => {
                const nonArchived = allSurveys.filter((s: Survey) => !s.archived)
                if (!searchTerm) {
                    return nonArchived
                }
                return new Fuse(nonArchived, {
                    threshold: 0.3,
                    keys: ['name'],
                })
                    .search(searchTerm)
                    .map(({ item }) => item)
            },
        ],
    }),
])
