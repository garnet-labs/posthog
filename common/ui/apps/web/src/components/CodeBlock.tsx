import * as React from 'react'
import { codeToHtml } from 'shiki'

interface CodeBlockProps {
    code: string
    language?: string
}

export function CodeBlock({ code, language = 'tsx' }: CodeBlockProps): React.ReactElement {
    const [html, setHtml] = React.useState<string>('')

    React.useEffect(() => {
        codeToHtml(code.trim(), {
            lang: language,
            theme: 'github-dark-default',
        }).then(setHtml)
    }, [code, language])

    if (!html) {
        return (
            <pre className="overflow-x-auto rounded-md bg-[#0d1117] p-4 text-sm">
                <code>{code.trim()}</code>
            </pre>
        )
    }

    return <div className="overflow-x-auto rounded-md text-sm [&_pre]:p-4" dangerouslySetInnerHTML={{ __html: html }} />
}
