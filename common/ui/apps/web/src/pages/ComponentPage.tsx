import * as React from 'react'

import { Separator } from '@posthog/ui-primitives'

import { CodeBlock } from '../components/CodeBlock'
import { ComponentPreview } from '../components/ComponentPreview'
import { PropsTable } from '../components/PropsTable'
import { registry } from '../registry/registry'

interface ComponentPageProps {
    slug: string
}

export function ComponentPage({ slug }: ComponentPageProps): React.ReactElement {
    const entry = registry.find((e) => e.slug === slug)

    if (!entry) {
        return (
            <div className="py-12 text-center">
                <h1 className="text-2xl font-bold">Component not found</h1>
                <p className="mt-2 text-muted-foreground">No component with slug &quot;{slug}&quot;.</p>
            </div>
        )
    }

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-3xl font-bold">{entry.name}</h1>
                <p className="mt-2 text-lg text-muted-foreground">{entry.description}</p>
            </div>

            <Separator />

            <section>
                <h2 id="examples" className="mb-4 text-2xl font-semibold">
                    Examples
                </h2>
                <div className="space-y-8">
                    {entry.examples.map((example) => (
                        <ComponentPreview key={example.name} example={example} />
                    ))}
                </div>
            </section>

            {entry.anatomy && (
                <>
                    <Separator />
                    <section>
                        <h2 id="anatomy" className="mb-4 text-2xl font-semibold">
                            Anatomy
                        </h2>
                        <p className="mb-4 text-sm text-muted-foreground">
                            Import the component and assemble its parts:
                        </p>
                        <CodeBlock code={entry.anatomy} />
                    </section>
                </>
            )}

            {entry.props.length > 0 && (
                <>
                    <Separator />
                    <section>
                        <h2 id="api-reference" className="mb-4 text-2xl font-semibold">
                            API reference
                        </h2>
                        <PropsTable props={entry.props} />
                    </section>
                </>
            )}
        </div>
    )
}
