import { useActions, useValues } from 'kea'
import { useEffect } from 'react'

import { IconDocument } from '@posthog/icons'
import { Spinner } from '@posthog/lemon-ui'

import { hogbotResearchLogic } from './hogbotResearchLogic'
import { ResearchDocument } from './ResearchDocument'

export function HogbotResearch(): JSX.Element {
    const { files, filesLoading, selectedFilePath, selectedFile, fileContent, fileContentLoading } =
        useValues(hogbotResearchLogic)
    const { loadFiles, selectFile, loadFileContent } = useActions(hogbotResearchLogic)

    useEffect(() => {
        loadFiles()
    }, [])

    useEffect(() => {
        if (selectedFile) {
            loadFileContent()
        }
    }, [selectedFile?.path])

    if (filesLoading) {
        return (
            <div className="flex items-center justify-center py-20">
                <Spinner className="text-2xl" />
            </div>
        )
    }

    if (files.length === 0) {
        return (
            <div className="flex items-center justify-center py-20 text-muted">
                No research documents yet. Hogbot will create documents as it investigates.
            </div>
        )
    }

    const activePath = selectedFilePath ?? files[0]?.path

    return (
        <div className="flex border rounded-lg overflow-hidden h-[calc(100vh-12rem)]">
            <div className="w-1/4 min-w-[200px] border-r overflow-y-auto bg-surface-primary">
                {files.map((file) => (
                    <button
                        key={file.path}
                        type="button"
                        className={`w-full text-left px-3 py-3 border-b cursor-pointer hover:bg-primary-alt-highlight transition-colors ${
                            activePath === file.path ? 'bg-primary-alt-highlight' : ''
                        }`}
                        onClick={() => selectFile(file.path)}
                    >
                        <div className="flex items-center gap-2 mb-1">
                            <IconDocument className="text-muted shrink-0" />
                            <span className="text-sm font-medium truncate">{file.filename}</span>
                        </div>
                        <div className="text-xs text-muted-alt mt-1">
                            {new Date(file.modified_at).toLocaleString()}
                        </div>
                    </button>
                ))}
            </div>
            <div className="flex-1 p-4 overflow-y-auto">
                {selectedFile ? (
                    <ResearchDocument
                        file={selectedFile}
                        content={fileContent}
                        contentLoading={fileContentLoading}
                    />
                ) : (
                    <div className="flex items-center justify-center h-full text-muted">
                        Select a document to view
                    </div>
                )}
            </div>
        </div>
    )
}
