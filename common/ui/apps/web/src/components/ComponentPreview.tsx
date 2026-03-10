import * as React from 'react'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@posthog/ui-primitives'

import type { ComponentExample } from '../registry/types'
import { CodeBlock } from './CodeBlock'

interface ComponentPreviewProps {
    example: ComponentExample
}

export function ComponentPreview({ example }: ComponentPreviewProps): React.ReactElement {
    const ExampleComponent = example.component

    return (
        <div className="space-y-2">
            <h3 id={example.name.toLowerCase().replace(/\s+/g, '-')} className="text-lg font-medium">
                {example.name}
            </h3>
            <Tabs defaultValue="preview" className="w-full">
                <TabsList>
                    <TabsTrigger value="preview">Preview</TabsTrigger>
                    <TabsTrigger value="code">Code</TabsTrigger>
                </TabsList>
                <TabsContent value="preview">
                    <div className="flex min-h-[150px] items-center justify-center rounded-md border border-border p-8">
                        <React.Suspense fallback={<div className="text-sm text-muted-foreground">Loading...</div>}>
                            <ExampleComponent />
                        </React.Suspense>
                    </div>
                </TabsContent>
                <TabsContent value="code">
                    <CodeBlock code={example.code} />
                </TabsContent>
            </Tabs>
        </div>
    )
}
