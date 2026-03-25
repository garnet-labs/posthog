import { TZLabel } from 'lib/components/TZLabel'
import { LemonMarkdown } from 'lib/lemon-ui/LemonMarkdown'

import { ResearchDocument as ResearchDocumentType } from '../types'

export interface ResearchDocumentProps {
    document: ResearchDocumentType
}

export function ResearchDocument({ document }: ResearchDocumentProps): JSX.Element {
    return (
        <div className="flex flex-col h-full">
            <div className="border-b pb-3 mb-4">
                <h2 className="text-lg font-semibold mb-1">{document.title}</h2>
                <div className="flex items-center gap-3 text-xs text-muted">
                    <span className="font-mono">{document.filename}</span>
                    <span>
                        Updated <TZLabel time={document.updated_at} />
                    </span>
                </div>
            </div>
            <div className="flex-1 overflow-y-auto">
                <LemonMarkdown>{document.content}</LemonMarkdown>
            </div>
        </div>
    )
}
