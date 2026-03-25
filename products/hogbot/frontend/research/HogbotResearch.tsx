import { useActions, useValues } from 'kea'
import { useEffect } from 'react'

import { IconDocument } from '@posthog/icons'
import { Spinner } from '@posthog/lemon-ui'

import { TZLabel } from 'lib/components/TZLabel'

import { hogbotResearchLogic } from './hogbotResearchLogic'
import { ResearchDocument } from './ResearchDocument'

export function HogbotResearch(): JSX.Element {
    const { documents, documentsLoading, selectedDocumentId, selectedDocument } = useValues(hogbotResearchLogic)
    const { loadDocuments, selectDocument } = useActions(hogbotResearchLogic)

    useEffect(() => {
        loadDocuments()
    }, [])

    if (documentsLoading) {
        return (
            <div className="flex items-center justify-center py-20">
                <Spinner className="text-2xl" />
            </div>
        )
    }

    if (documents.length === 0) {
        return (
            <div className="flex items-center justify-center py-20 text-muted">
                No research documents yet. Hogbot will create documents as it investigates.
            </div>
        )
    }

    const activeId = selectedDocumentId ?? documents[0]?.id

    return (
        <div className="flex border rounded-lg overflow-hidden" style={{ height: '600px' }}>
            <div className="w-1/4 min-w-[200px] border-r overflow-y-auto bg-surface-primary">
                {documents.map((doc) => (
                    <button
                        key={doc.id}
                        type="button"
                        className={`w-full text-left px-3 py-3 border-b cursor-pointer hover:bg-primary-alt-highlight transition-colors ${
                            activeId === doc.id ? 'bg-primary-alt-highlight' : ''
                        }`}
                        onClick={() => selectDocument(doc.id)}
                    >
                        <div className="flex items-center gap-2 mb-1">
                            <IconDocument className="text-muted shrink-0" />
                            <span className="text-sm font-medium truncate">{doc.filename}</span>
                        </div>
                        <div className="text-xs text-muted truncate">{doc.title}</div>
                        <div className="text-xs text-muted-alt mt-1">
                            <TZLabel time={doc.updated_at} />
                        </div>
                    </button>
                ))}
            </div>
            <div className="flex-1 p-4 overflow-y-auto">
                {selectedDocument ? (
                    <ResearchDocument document={selectedDocument} />
                ) : (
                    <div className="flex items-center justify-center h-full text-muted">
                        Select a document to view
                    </div>
                )}
            </div>
        </div>
    )
}
