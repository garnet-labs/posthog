import { Spinner } from '@posthog/lemon-ui'

import { LemonMarkdown } from 'lib/lemon-ui/LemonMarkdown'

import { SandboxFile } from '../types'

export interface ResearchDocumentProps {
    file: SandboxFile
    content: string
    contentLoading: boolean
}

export function ResearchDocument({ file, content, contentLoading }: ResearchDocumentProps): JSX.Element {
    return (
        <div className="flex flex-col h-full">
            <div className="border-b pb-3 mb-4">
                <h2 className="text-lg font-semibold mb-1">{file.filename}</h2>
                <div className="flex items-center gap-3 text-xs text-muted">
                    <span className="font-mono">{file.path}</span>
                    <span>{new Date(file.modified_at).toLocaleString()}</span>
                </div>
            </div>
            <div className="flex-1 overflow-y-auto">
                {contentLoading ? (
                    <div className="flex items-center justify-center py-10">
                        <Spinner className="text-xl" />
                    </div>
                ) : content ? (
                    <LemonMarkdown>{content}</LemonMarkdown>
                ) : (
                    <div className="text-muted">Empty file</div>
                )}
            </div>
        </div>
    )
}
