import { actions, kea, path, reducers, selectors } from 'kea'
import { loaders } from 'kea-loaders'

// import api from 'lib/api'

import { MOCK_FILE_CONTENTS, MOCK_SANDBOX_FILES } from '../__mocks__/researchMocks'
import { SandboxFile } from '../types'
import type { hogbotResearchLogicType } from './hogbotResearchLogicType'

export const hogbotResearchLogic = kea<hogbotResearchLogicType>([
    path(['products', 'hogbot', 'frontend', 'research', 'hogbotResearchLogic']),
    actions({
        selectFile: (path: string | null) => ({ path }),
    }),
    loaders(({ values }) => ({
        files: [
            [] as SandboxFile[],
            {
                loadFiles: async (): Promise<SandboxFile[]> => {
                    // TODO: Replace with API call when backend is ready
                    // Lists .md files from the sandbox filesystem
                    // const response = await api.get(`api/projects/@current/hogbot/files/`, {
                    //     data: { glob: '/research/*.md' },
                    // })
                    // return response.results
                    return MOCK_SANDBOX_FILES
                },
            },
        ],
        fileContent: [
            '' as string,
            {
                loadFileContent: async (): Promise<string> => {
                    const filePath = values.selectedFilePath
                    if (!filePath) {
                        return ''
                    }
                    // TODO: Replace with API call when backend is ready
                    // Reads a single file from the sandbox filesystem
                    // const response = await api.get(
                    //     `api/projects/@current/hogbot/files/read/`,
                    //     { data: { path: filePath }, responseType: 'text' }
                    // )
                    // return response
                    return MOCK_FILE_CONTENTS[filePath] ?? ''
                },
            },
        ],
    })),
    reducers({
        selectedFilePath: [
            null as string | null,
            {
                selectFile: (_, { path }) => path,
            },
        ],
    }),
    selectors({
        selectedFile: [
            (s) => [s.files, s.selectedFilePath],
            (files, selectedFilePath): SandboxFile | null => {
                const path = selectedFilePath ?? files[0]?.path
                if (!path) {
                    return null
                }
                return files.find((f) => f.path === path) ?? null
            },
        ],
    }),
])
