import { actions, kea, path, reducers, selectors } from 'kea'
import { loaders } from 'kea-loaders'

// import api from 'lib/api'

import { MOCK_RESEARCH_DOCUMENTS } from '../__mocks__/researchMocks'
import { ResearchDocument } from '../types'
import type { hogbotResearchLogicType } from './hogbotResearchLogicType'

export const hogbotResearchLogic = kea<hogbotResearchLogicType>([
    path(['products', 'hogbot', 'frontend', 'research', 'hogbotResearchLogic']),
    actions({
        selectDocument: (id: string | null) => ({ id }),
    }),
    loaders({
        documents: [
            [] as ResearchDocument[],
            {
                loadDocuments: async (): Promise<ResearchDocument[]> => {
                    // TODO: Replace with API call when backend is ready
                    // const response = await api.get(`api/projects/@current/hogbot/research/`)
                    // return response.results
                    return MOCK_RESEARCH_DOCUMENTS
                },
            },
        ],
    }),
    reducers({
        selectedDocumentId: [
            null as string | null,
            {
                selectDocument: (_, { id }) => id,
            },
        ],
    }),
    selectors({
        selectedDocument: [
            (s) => [s.documents, s.selectedDocumentId],
            (documents, selectedDocumentId): ResearchDocument | null => {
                if (!selectedDocumentId) {
                    return documents[0] ?? null
                }
                return documents.find((d) => d.id === selectedDocumentId) ?? null
            },
        ],
    }),
])
