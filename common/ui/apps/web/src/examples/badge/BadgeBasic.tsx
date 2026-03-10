import { Badge } from '@posthog/ui-primitives'

export default function BadgeBasic(): React.ReactElement {
    return (
        <div className="flex gap-2">
            <Badge>Default</Badge>
            <Badge variant="secondary">Secondary</Badge>
            <Badge variant="outline">Outline</Badge>
            <Badge variant="destructive">Destructive</Badge>
        </div>
    )
}
