import { ToggleGroup, ToggleGroupItem } from '@posthog/ui-primitives'

export default function ToggleGroupBasic(): React.ReactElement {
    return (
        <div className="flex flex-col gap-4">
            <ToggleGroup defaultValue={['center']} spacing={0}>
                <ToggleGroupItem value="left">Left</ToggleGroupItem>
                <ToggleGroupItem value="center">Center</ToggleGroupItem>
                <ToggleGroupItem value="right">Right</ToggleGroupItem>
            </ToggleGroup>
            <ToggleGroup variant="outline">
                <ToggleGroupItem value="bold">Bold</ToggleGroupItem>
                <ToggleGroupItem value="italic">Italic</ToggleGroupItem>
                <ToggleGroupItem value="underline">Underline</ToggleGroupItem>
            </ToggleGroup>
        </div>
    )
}
