import { actions, kea, path, reducers, selectors } from 'kea'
import { loaders } from 'kea-loaders'

import api from 'lib/api'

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
                    const response = await api.get(
                        `api/projects/@current/hogbot/files/?glob=${encodeURIComponent('/research/*.md')}`
                    )
                    return response.results
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
                    const response = await api.getResponse(
                        `api/projects/@current/hogbot/files/read/?path=${encodeURIComponent(filePath)}`
                    )
                    return await response.text()
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
