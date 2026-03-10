import { Button } from '@posthog/ui-primitives'

export default function ButtonSizes(): React.ReactElement {
    return (
        <div className="flex flex-wrap items-center gap-2">
            <Button size="xs">Extra small</Button>
            <Button size="sm">Small</Button>
            <Button size="default">Default</Button>
            <Button size="lg">Large</Button>
        </div>
    )
}
