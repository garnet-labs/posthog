import * as React from 'react'

import type { ComponentProp } from '../registry/types'

interface PropsTableProps {
    props: ComponentProp[]
}

export function PropsTable({ props }: PropsTableProps): React.ReactElement | null {
    if (props.length === 0) {
        return null
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-border">
                        <th className="py-2 pr-4 text-left font-medium">Prop</th>
                        <th className="py-2 pr-4 text-left font-medium">Type</th>
                        <th className="py-2 pr-4 text-left font-medium">Default</th>
                        <th className="py-2 text-left font-medium">Description</th>
                    </tr>
                </thead>
                <tbody>
                    {props.map((prop) => (
                        <tr key={prop.name} className="border-b border-border">
                            <td className="py-2 pr-4 font-mono text-xs">{prop.name}</td>
                            <td className="py-2 pr-4 font-mono text-xs text-muted-foreground">{prop.type}</td>
                            <td className="py-2 pr-4 font-mono text-xs text-muted-foreground">{prop.default ?? '—'}</td>
                            <td className="py-2 text-muted-foreground">{prop.description}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}
